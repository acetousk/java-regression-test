"""Share dependency artifacts, not stale workspace outputs, between checkouts."""

import fcntl
import json
from pathlib import Path
import shutil
import subprocess


def build(command, directory, environment, private):
    target = Path(environment["CARGO_TARGET_DIR"])
    if not target.is_absolute():
        target = directory / target
    target.mkdir(parents=True, exist_ok=True)
    # Hold through the copy, not just cargo build. All shared-cache builds must
    # use this wrapper; Cargo's own lock ends before an executable can be copied.
    with (target / ".moqui-build.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        owner = str(directory.resolve()) + " "  # Same protocol as shared-cache moq.
        marker = target / ".moqui-checkout"
        if not marker.exists() or marker.read_text() != owner:
            # Cargo can falsely report path packages fresh after A -> B -> A.
            # Invalidate only local packages; registry/git dependencies stay warm.
            metadata = json.loads(subprocess.check_output(
                ["cargo", "metadata", "--format-version", "1", "--locked"],
                cwd=directory, env=environment, text=True))
            packages = [package["name"] for package in metadata["packages"] if package["source"] is None]
            if not packages:
                raise RuntimeError("Cargo metadata contains no local packages")
            clean = ["cargo", "clean"]
            for package in packages:
                clean.extend(["-p", package])
            subprocess.run(clean, cwd=directory, env=environment, check=True)
            marker.write_text(owner)
        subprocess.run(command, cwd=directory, env=environment, check=True)
        source = target / "debug/moqui"
        private.parent.mkdir(parents=True, exist_ok=True)
        temporary = private.with_suffix(".tmp")
        shutil.copy2(source, temporary)
        temporary.replace(private)
