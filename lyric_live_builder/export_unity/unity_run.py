"""Batch-mode build in a closed project (design §9.6): start Unity, then poll it without blocking Blender."""
import os
import subprocess

METHOD = "LyricLive.Editor.LLBBuilder.BuildFromCommandLine"


class BatchBuild:
    def __init__(self, unity, project, song_rel):
        self.log = os.path.join(project, "Logs", "llb_build.log")
        os.makedirs(os.path.dirname(self.log), exist_ok=True)
        if os.path.exists(self.log):
            os.remove(self.log)
        cmd = [unity, "-batchmode", "-nographics", "-quit", "-projectPath", project,
               "-executeMethod", METHOD, "-llbSong", song_rel, "-logFile", self.log]
        self.proc = subprocess.Popen(cmd)
        self._seen = 0

    def poll(self):
        """(finished, return code or None, new [LLB] lines)."""
        lines = []
        try:
            with open(self.log, "rb") as f:
                f.seek(self._seen)
                data = f.read()
            cut = data.rfind(b"\n") + 1                      # only whole lines; the rest comes next time
            self._seen += cut
            chunk = data[:cut].decode("utf-8", errors="replace")
            lines = [ln.strip() for ln in chunk.splitlines() if ln.strip().startswith("[LLB]")]
        except OSError:
            pass
        code = self.proc.poll()
        return code is not None, code, lines

    def cancel(self):
        if self.proc.poll() is None:
            self.proc.terminate()
