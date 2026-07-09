import os
import re
import zipfile

from minecraft_fontgen.config import RESOLVED_TEXTURE_DIR, WORK_DIR
from minecraft_fontgen.functions import log, parse_json

_NAMESPACE_RE = re.compile(r"^[a-z0-9_.-]+$")
_PATH_RE = re.compile(r"^[a-z0-9_./-]+$")


def split_resource_ref(ref, default_namespace="minecraft"):
    """Splits a Minecraft resource location like 'ns:path/file.png' into (namespace, path).

    Rejects refs whose characters fall outside the ResourceLocation grammar and
    any path segment that could escape the pack root ('..', '.', empty)."""
    namespace, sep, path = ref.partition(":")
    if not sep:
        namespace, path = default_namespace, ref
    if not _NAMESPACE_RE.match(namespace):
        raise ValueError(f"invalid namespace '{namespace}'")
    if not path or not _PATH_RE.match(path):
        raise ValueError(f"invalid path '{path}'")
    if any(segment in ("", ".", "..") for segment in path.split("/")):
        raise ValueError(f"unsafe path '{path}'")
    return namespace, path


def sanitize_fs_name(name):
    """Reduces a string to a Windows-safe directory name."""
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_") or "pack"
