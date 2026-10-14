"""Pure source composition controls; no compiler/runtime execution."""
import json
import unittest
import tempfile
from unittest.mock import patch
from types import SimpleNamespace
import control
from pathlib import Path
from control import (PACKAGE, SAVEFILE, MANAGER, COMPOSED_MANAGER_SHA,
                     COMPOSED_SAVEFILE_SHA, OLD_DECODE, NEW_DECODE, sha, lf,
                     compose_savefile, authenticate_savefile, target_sources)

class SourceCompositionTests(unittest.TestCase):
    def setUp(self):
        self.frozen=(PACKAGE/'frozen/candidate'/SAVEFILE).read_bytes()
        self.current=(PACKAGE.parents[1]/SAVEFILE).read_bytes()
    def test_exact_old_and_composed_source_only(self):
        self.assertFalse(authenticate_savefile(self.frozen,self.frozen))
        self.assertTrue(authenticate_savefile(self.current,self.frozen))
        self.assertEqual(sha(lf(self.current)),COMPOSED_SAVEFILE_SHA)
        self.assertEqual(lf(self.current).replace(NEW_DECODE,OLD_DECODE),lf(self.frozen))
    def test_any_other_method_change_rejected(self):
        for mutation in (self.current+b'\n',self.current.replace(b'Savefiles.Remove(this)',b'Savefiles.Clear()'),self.current.replace(NEW_DECODE,NEW_DECODE+b'/* changed */')):
            with self.assertRaises(AssertionError): authenticate_savefile(mutation,self.frozen)
    def test_duplicate_or_missing_seam_rejected(self):
        for mutation in (lf(self.frozen).replace(OLD_DECODE,b'other'),lf(self.frozen)+OLD_DECODE):
            with self.assertRaises(AssertionError): compose_savefile(mutation)
    def test_all_negative_controls_preserve_prior_exact_mutation(self):
        modes=['positive',*json.loads((PACKAGE/'controls.json').read_text())]
        for mode in modes:
            with self.subTest(mode=mode):
                old=target_sources(mode);composed=target_sources(mode,True)
                self.assertEqual(set(old),set(composed))
                for path,raw in old.items():
                    if path==SAVEFILE:
                        self.assertEqual(composed[path].replace(NEW_DECODE,OLD_DECODE),lf(raw))
                    else:self.assertEqual(composed[path],raw)
    def test_original_remains_exact_historical_bytes(self):
        self.assertEqual(target_sources('original'),target_sources('original',True))
    def test_exact_manager_binding(self):
        raw=lf((PACKAGE.parents[1]/MANAGER).read_bytes())
        self.assertEqual(sha(raw),COMPOSED_MANAGER_SHA)
        self.assertNotEqual(sha(raw+b'\n'),COMPOSED_MANAGER_SHA)

    def test_prepare_verify_restore_all_modes_with_exact_fake_git_bytes(self):
        # A fake immutable Git transport exercises actual receipt/file logic only.
        manifest,_=control.frozen_inputs()
        inputs=['.gitattributes','manifest.json',*control.PACKAGE_CODE,*manifest['files']]
        engine=PACKAGE.parents[1]
        head='a'*40
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            package=root/'tools/save_cost_profile'
            snapshots={}
            for name in inputs:
                path=package/name;path.parent.mkdir(parents=True,exist_ok=True)
                raw=(PACKAGE/name).read_bytes();path.write_bytes(raw)
                snapshots['tools/save_cost_profile/'+name]=raw
            paths=[*control.RUNTIME,control.HOST,control.SMOKE,control.MANAGER,'Content.IntegrationTests/Content.IntegrationTests.csproj']
            for name in paths:
                raw=control.lf((engine/name).read_bytes());snapshots[name]=raw
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
            historical={name:(PACKAGE/'frozen/original'/name).read_bytes() for name in (SAVEFILE,control.RESOURCE,control.SEAM)}
            def fake_git(where,*args):
                if args==('rev-parse','HEAD'):return ((control.ROBUST if where==root/'RobustToolbox' else head)+'\n').encode()
                if args[0]=='merge-base':return b''
                if args[0]=='show':
                    revision,name=args[1].split(':',1)
                    return historical[name] if revision==control.BASE else snapshots[name]
                raise AssertionError(args)
            with patch.object(control,'PACKAGE',package),patch.object(control,'git',fake_git),patch.object(control.subprocess,'run',return_value=SimpleNamespace(returncode=1)):
                for mode in ['positive','original',*json.loads((package/'controls.json').read_text())]:
                    with self.subTest(mode=mode):
                        receipt=root/'receipts'/mode/'receipt.json'
                        control.prepare(root,mode,head,receipt)
                        data=control.verify_receipt(root,mode,head,receipt)
                        self.assertTrue(data['composed_savefile'])
                        self.assertIn(MANAGER,data['reviewed_head_sources'])
                        manager=root/MANAGER;manager.write_bytes(snapshots[MANAGER]+b'changed')
                        with self.assertRaises(AssertionError):control.verify_receipt(root,mode,head,receipt)
                        manager.write_bytes(snapshots[MANAGER])
                        control.restore(root,mode,head,receipt)
                        self.assertEqual((root/SAVEFILE).read_bytes(),snapshots[SAVEFILE])
