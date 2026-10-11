"""Cache command/API fixtures; these do not qualify a BuildKit backend."""

import json
import pathlib
import sys
import tempfile


class CacheTools:
    def __init__(self):
        self.root = tempfile.TemporaryDirectory(prefix="ci-utils-cache-", dir="/tmp")
        self.path = pathlib.Path(self.root.name)
        self.state_path = self.path / "state.json"
        self.calls_path = self.path / "calls.jsonl"
        self.prunes = []
        self.state = {
            "capabilities": {
                "daemon_id": "fixture-daemon",
                "builder": "default",
                "driver": "docker",
                "worker_id": "worker",
                "gc_space_filters": True,
                "buildkit_version": "v0.29.0",
            },
            "records": [
                {
                    "ID": "old",
                    "Size": 512,
                    "InUse": False,
                    "Shared": False,
                    "Type": "regular",
                    "LastUsedAt": "2026-01-01T00:00:00Z",
                }
            ],
            "after_age": [],
            "after_budget": [],
            "driver": "docker",
        }
        program = f"""#!{sys.executable}
import json, pathlib, sys
state_path = pathlib.Path({str(self.state_path)!r})
calls_path = pathlib.Path({str(self.calls_path)!r})
state = json.loads(state_path.read_text())
args = sys.argv[1:]
with calls_path.open("a") as out:
    out.write(json.dumps([pathlib.Path(sys.argv[0]).name, *args]) + "\\n")
if pathlib.Path(sys.argv[0]).name == "ci-buildkit-probe":
    print(json.dumps(state["capabilities"]))
elif "version" in args or "--version" in args:
    print("github.com/docker/buildx v0.38.0 fixture" if "buildx" in args else "Docker version 29.9.0")
elif "inspect" in args:
    print("Name: default\\nDriver: " + state["driver"] + "\\n\\nNodes:\\nName: default\\nEndpoint: default\\nStatus: running\\nBuildKit version: v0.29.0")
elif "du" in args:
    for record in state["records"]:
        print(json.dumps({{**record, "Size": "512B", "LastUsedAt": "9 months ago", "Reclaimable": not record["InUse"]}}))
else:
    sys.exit(2)
"""
        for name in ("docker", "ci-buildkit-probe"):
            target = self.path / name
            target.write_text(program)
            target.chmod(0o755)
        self.save()

    def save(self):
        self.state_path.write_text(json.dumps(self.state))

    def routes(self):
        def prune(form):
            self.prunes.append(form)
            state = json.loads(self.state_path.read_text())
            state["records"] = (
                state["after_budget"]
                if "max-used-space" in form
                else state["after_age"]
            )
            self.state_path.write_text(json.dumps(state))
            return 200, {"SpaceReclaimed": 0, "CachesDeleted": None}

        return {
            ("GET", "/v1.48/system/df?type=build-cache"): lambda: (
                200,
                {"BuildCache": json.loads(self.state_path.read_text())["records"]},
            ),
            ("POST", "/v1.48/build/prune"): prune,
        }

    def calls(self):
        return (
            [json.loads(line) for line in self.calls_path.read_text().splitlines()]
            if self.calls_path.exists()
            else []
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.root.cleanup()
