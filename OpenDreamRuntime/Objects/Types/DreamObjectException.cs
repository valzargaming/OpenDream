namespace OpenDreamRuntime.Objects.Types;

public sealed class DreamObjectException(DreamObjectDefinition objectDefinition) : DreamObject(objectDefinition) {
    public DreamValue Name = DreamValue.Null;
    public DreamValue Desc = DreamValue.Null;
    public DreamValue File = DreamValue.Null;
    public DreamValue Line = DreamValue.False;

    //TODO: Match the format of BYOND exceptions since SS13 does splittext and other things to extract data from exceptions

    protected override void HandleDeletion() {
        // These native fields own references just like ordinary datum variables.
        // Clear them before release to make recursive deletion harmless.
        var name = Name;
        var desc = Desc;
        var file = File;
        var line = Line;
        Name = Desc = File = Line = DreamValue.Null;
        try { name.Dispose(); }
        finally {
            try { desc.Dispose(); }
            finally {
                try { file.Dispose(); }
                finally {
                    try { line.Dispose(); }
                    finally { base.HandleDeletion(); }
                }
            }
        }
    }

    protected override void SetVar(string varName, DreamValue value) {
        switch (varName) {
            case "name":
                value.IncRef();
                Name.DecRef();
                Name = value;
                return;
            case "desc":
                value.IncRef();
                Desc.DecRef();
                Desc = value;
                return;
            case "file":
                value.IncRef();
                File.DecRef();
                File = value;
                return;
            case "line":
                value.IncRef();
                Line.DecRef();
                Line = value;
                return;
            default:
                base.SetVar(varName, value);
                return;
        }
    }

    protected override bool TryGetVar(string varName, out DreamValue value) {
        switch (varName) {
            case "name":
                Name.IncRef();
                value = Name;
                return true;
            case "desc":
                Desc.IncRef();
                value = Desc;
                return true;
            case "file":
                File.IncRef();
                value = File;
                return true;
            case "line":
                Line.IncRef();
                value = Line;
                return true;
            default:
                return base.TryGetVar(varName, out value);
        }
    }
}
