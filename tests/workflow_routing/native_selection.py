"""Offline checks for this workflow's restricted YAML/Actions expression subset.

This is not an Actions runner or a general YAML parser. Unsupported shapes fail
closed. GitHub's PR changed files come from base...head, not old-head..new-head.
No network, compiler, SDK or process other than local Git is invoked.
"""
import argparse
import ast
import json
from pathlib import Path
import re
import subprocess


WORKFLOW = '.github/workflows/native-byond-proof.yml'


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root).decode().strip()


def pr_diff(root, base, head):
    merge_base = git(root, 'merge-base', base, head)
    paths = git(root, 'diff', '--name-only', f'{base}...{head}').splitlines()
    return merge_base, paths


def block(text, indent, name):
    lines = text.splitlines()
    start = lines.index(' ' * indent + name + ':') + 1
    end = start
    while end < len(lines):
        line = lines[end]
        if line.strip() and not line.lstrip().startswith('#'):
            if len(line) - len(line.lstrip()) <= indent:
                break
        end += 1
    return '\n'.join(lines[start:end])


def pr_patterns(text):
    event = block(block(text, 0, 'on'), 2, 'pull_request')
    match = re.search(r'^    paths: (\[.*\])$', event, re.M)
    if not match:
        raise ValueError('Expected the reviewed inline PR paths list')
    paths = ast.literal_eval(match[1])
    if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
        raise ValueError('Invalid paths')
    # These are the only patterns used here; other Actions pattern syntax needs review.
    if any(re.search(r'[^A-Za-z0-9_./*\-]', p) for p in paths):
        raise ValueError('Unsupported path pattern')
    return paths


def path_matches(path, pattern):
    # Single-star stays in a path component; double-star crosses directories.
    parts = pattern.split('**')
    expression = '.*'.join(''.join('[^/]*' if c == '*' else re.escape(c)
                                  for c in part) for part in parts)
    return re.fullmatch(expression, path) is not None


def native_input_default(text):
    dispatch = block(block(text, 0, 'on'), 2, 'workflow_dispatch')
    inputs = block(dispatch, 4, 'inputs')
    value = block(inputs, 6, 'native_compile_authorized_sha')
    if '        type: string' not in value or '        required: false' not in value:
        raise ValueError('Expected optional exact-SHA string input')
    defaults = re.findall(r'^        default: (.*)$', value, re.M)
    if len(defaults) != 1:
        raise ValueError('Expected one explicit default')
    return ast.literal_eval(defaults[0])


def condition(text, job):
    body = block(block(text, 0, 'jobs'), 2, job)
    values = re.findall(r'^    if: (.+)$', body, re.M)
    if len(values) > 1:
        raise ValueError('Duplicate job condition')
    return values[0] if values else None


def evaluate(expression, context):
    """Evaluate a small, explicit expression subset from the actual job condition."""
    if expression is None:
        return True  # Actions' default for a successful workflow with no job guard.
    expression = expression.removeprefix('${{').removesuffix('}}').strip()
    # Tokenize before translating so literals cannot be rewritten as operators.
    tokens = re.findall(r"'[^']*'|[A-Za-z_][A-Za-z0-9_.]*|&&|\|\||==|!=|[()]|\S", expression)
    names = {}
    translated = []
    for token in tokens:
        if token in ('&&', '||'):
            translated.append({'&&': 'and', '||': 'or'}[token])
        elif re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.]*', token):
            if token not in context:
                raise ValueError(f'Unsupported context: {token}')
            name = f'value{len(names)}'
            names[name] = context[token]
            translated.append(name)
        elif token.startswith("'") or token in ('==', '!=', '(', ')'):
            translated.append(token)
        else:
            raise ValueError(f'Unsupported token: {token}')
    tree = ast.parse(' '.join(translated), mode='eval')

    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Name):
            return names[node.id]
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.BoolOp):
            values = [visit(v) for v in node.values]
            return all(values) if isinstance(node.op, ast.And) else any(values)
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            left, right = visit(node.left), visit(node.comparators[0])
            if isinstance(node.ops[0], ast.Eq):
                return left == right
            if isinstance(node.ops[0], ast.NotEq):
                return left != right
        raise ValueError('Unsupported expression shape')

    return bool(visit(tree))


def selected_jobs(text, event, sha, authorized_sha=None):
    context = {'github.event_name': event, 'github.sha': sha,
               'inputs.native_compile_authorized_sha': native_input_default(text)
               if authorized_sha is None else authorized_sha}
    jobs = re.findall(r'^  ([A-Za-z0-9_-]+):$', block(text, 0, 'jobs'), re.M)
    return {job: evaluate(condition(text, job), context) for job in jobs}


def report(root, base, head):
    merge_base, paths = pr_diff(root, base, head)
    text = git(root, 'show', f'{head}:{WORKFLOW}')
    patterns = pr_patterns(text)
    matches = [p for p in paths if any(path_matches(p, pattern) for pattern in patterns)]
    sha = git(root, 'rev-parse', head)
    return {'base': git(root, 'rev-parse', base), 'head': sha, 'merge_base': merge_base,
            'diff_semantics': 'git diff --name-only base...head', 'changed_paths': paths,
            'native_workflow_matches': matches, 'workflow_selected': bool(matches),
            'pull_request_jobs': selected_jobs(text, 'pull_request', sha),
            'manual_default_jobs': selected_jobs(text, 'workflow_dispatch', sha),
            'manual_wrong_sha_jobs': selected_jobs(text, 'workflow_dispatch', sha, '0' * 40),
            'manual_exact_sha_jobs': selected_jobs(text, 'workflow_dispatch', sha, sha),
            'limit': 'Offline source selection only; exact SHA input is not authorization, execution, compiler acceptance or GitHub CI evidence.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, required=True)
    parser.add_argument('--base', required=True)
    parser.add_argument('--head', default='HEAD')
    args = parser.parse_args()
    print(json.dumps(report(args.repository, args.base, args.head), indent=2))
