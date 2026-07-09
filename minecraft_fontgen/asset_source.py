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
    if namespace in (".", ".."):
        raise ValueError(f"unsafe namespace '{namespace}'")
    if not path or not _PATH_RE.match(path):
        raise ValueError(f"invalid path '{path}'")
    if any(segment in ("", ".", "..") for segment in path.split("/")):
        raise ValueError(f"unsafe path '{path}'")
    return namespace, path


def sanitize_fs_name(name):
    """Reduces a string to a Windows-safe directory name."""
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_") or "pack"


class AssetSource:
    """One layer of Minecraft assets (the vanilla extraction or a resource pack)."""

    name = "asset-source"
    is_vanilla = False

    def get_font_json(self, font_id):
        raise NotImplementedError

    def get_texture(self, namespace, path):
        raise NotImplementedError

    def list_font_ids(self):
        raise NotImplementedError

    def read_mcmeta(self):
        return None

    def close(self):
        pass


class DirAssetSource(AssetSource):
    """Assets read from a directory containing assets/."""

    def __init__(self, root, name):
        self.root = root
        self.name = name

    def _read(self, *parts):
        path = os.path.join(self.root, *parts)
        if not os.path.isfile(path):
            return None
        with open(path, "rb") as f:
            return f.read()

    def get_font_json(self, font_id):
        namespace, path = split_resource_ref(font_id)
        return self._read("assets", namespace, "font", *f"{path}.json".split("/"))

    def get_texture(self, namespace, path):
        return self._read("assets", namespace, "textures", *path.split("/"))

    def list_font_ids(self):
        ids = []
        assets = os.path.join(self.root, "assets")
        if not os.path.isdir(assets):
            return ids
        for namespace in sorted(os.listdir(assets)):
            font_dir = os.path.join(assets, namespace, "font")
            if not os.path.isdir(font_dir):
                continue
            for dirpath, _dirs, files in os.walk(font_dir):
                for file in sorted(files):
                    if not file.endswith(".json"):
                        continue
                    rel = os.path.relpath(os.path.join(dirpath, file), font_dir)
                    ids.append(f"{namespace}:{rel[:-5].replace(os.sep, '/')}")
        return ids

    def read_mcmeta(self):
        return self._read("pack.mcmeta")


class ZipAssetSource(AssetSource):
    """Assets read from a resource pack zip, tolerating one nested root folder."""

    _FONT_JSON_RE = re.compile(r"^assets/([^/]+)/font/(.+)\.json$")

    def __init__(self, zip_path, name):
        self.name = name
        self._zf = zipfile.ZipFile(zip_path)
        normalized = [(n.replace("\\", "/"), n) for n in self._zf.namelist()]
        self._names = dict(normalized)
        self._prefix = self._detect_prefix(zip_path, list(self._names))

    @staticmethod
    def _detect_prefix(zip_path, names):
        if any(n == "pack.mcmeta" or n.startswith("assets/") for n in names):
            return ""
        tops = {n.split("/", 1)[0] for n in names if "/" in n}
        if len(tops) == 1:
            top = next(iter(tops))
            if any(n.startswith(f"{top}/assets/") or n == f"{top}/pack.mcmeta" for n in names):
                return f"{top}/"
        raise ValueError(f"'{zip_path}' contains no assets/ directory or pack.mcmeta")

    def _read(self, internal):
        original = self._names.get(self._prefix + internal)
        if original is None:
            return None
        return self._zf.read(original)

    def get_font_json(self, font_id):
        namespace, path = split_resource_ref(font_id)
        return self._read(f"assets/{namespace}/font/{path}.json")

    def get_texture(self, namespace, path):
        return self._read(f"assets/{namespace}/textures/{path}")

    def list_font_ids(self):
        ids = []
        for normalized in self._names:
            if not normalized.startswith(self._prefix):
                continue
            match = self._FONT_JSON_RE.match(normalized[len(self._prefix):])
            if match:
                ids.append(f"{match.group(1)}:{match.group(2)}")
        return ids

    def read_mcmeta(self):
        return self._read("pack.mcmeta")

    def close(self):
        self._zf.close()


def open_resource_pack(path):
    """Opens a resource pack zip or directory as an AssetSource."""
    label = sanitize_fs_name(os.path.splitext(os.path.basename(os.path.normpath(path)))[0])
    if os.path.isdir(path):
        root = path
        if not os.path.isdir(os.path.join(root, "assets")):
            nested = [c for c in os.listdir(root)
                      if os.path.isdir(os.path.join(root, c, "assets"))]
            if len(nested) != 1:
                raise ValueError(f"'{path}' does not contain an assets/ directory")
            root = os.path.join(root, nested[0])
        source = DirAssetSource(root, label)
    elif zipfile.is_zipfile(path):
        source = ZipAssetSource(path, label)
    else:
        raise ValueError(f"'{path}' is neither a resource pack zip nor a directory")

    raw = source.read_mcmeta()
    if raw is None:
        log(f"-> WARN Pack '{label}' has no pack.mcmeta, continuing anyway")
    else:
        try:
            meta = parse_json(raw.decode("utf-8", errors="replace").lstrip("﻿")).get("pack", {})
            log(f"-> PACK Pack '{label}' (pack_format {meta.get('pack_format', '?')})")
        except (ValueError, AttributeError):
            log(f"-> WARN Pack '{label}' has a malformed pack.mcmeta, continuing anyway")
    return source
