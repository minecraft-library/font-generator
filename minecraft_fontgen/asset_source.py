import os
import re
import zipfile

from minecraft_fontgen.config import RESOLVED_TEXTURE_DIR, VANILLA_PACK_ID, WORK_DIR
from minecraft_fontgen.functions import log, parse_json, sanitize_fs_name

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


class AssetSource:
    """One layer of Minecraft assets (the vanilla extraction or a resource pack)."""

    name = "asset-source"
    is_vanilla = False

    @property
    def pack_id(self):
        """The source's stable identity, used wherever font identity flows (colour
        grouping, per-pack output naming). Vanilla is not special-cased: it is just
        another identified source (see VanillaSource). Defaults to the source name."""
        return self.name

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
        namespace, path = split_resource_ref(f"{namespace}:{path}")
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
        namespace, path = split_resource_ref(f"{namespace}:{path}")
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
        log(f"→ ⚠️ Pack '{label}' has no pack.mcmeta, continuing anyway")
    else:
        try:
            meta = parse_json(raw.decode("utf-8", errors="replace").lstrip("\ufeff")).get("pack", {})
            log(f"→ 📦 Pack '{label}' (pack_format {meta.get('pack_format', '?')})")
        except (ValueError, AttributeError):
            log(f"→ ⚠️ Pack '{label}' has a malformed pack.mcmeta, continuing anyway")
    return source


class VanillaSource(DirAssetSource):
    """The vanilla layer: assets extracted from the client JAR into the work dir.

    Carries its own pack_id like any resource pack, so the mono/vanilla product is
    modelled as just another identified source rather than a special case."""

    is_vanilla = True

    def __init__(self, work_dir=WORK_DIR):
        super().__init__(work_dir, VANILLA_PACK_ID)


class AssetStack:
    """Ordered asset layers. Later sources take priority (later --resource-pack flags win)."""

    def __init__(self, sources):
        self.sources = list(sources)

    def pack_sources(self):
        return [s for s in self.sources if not s.is_vanilla]

    def font_json_layers(self, font_id):
        layers = []
        for source in self.sources:
            raw = source.get_font_json(font_id)
            if raw is not None:
                layers.append((source.name, raw))
        return layers

    def color_font_layers(self):
        """Enumerates every font file every resource pack ships, for the colour
        raster track. Yields (pack_name, font_id, raw_json) tuples with pack order
        preserved, each pack's font ids sorted and deduped, and vanilla excluded
        (it carries no colour cells). A grammar-invalid font id logs and skips
        rather than raising, so one malformed name never aborts the enumeration.
        This is the single seam both zip and dir sources feed."""
        layers = []
        for source in self.pack_sources():
            for font_id in sorted(set(source.list_font_ids())):
                try:
                    raw = source.get_font_json(font_id)
                except ValueError as error:
                    log(f" → ⚠️ Skipping font '{font_id}' in pack '{source.name}': {error}")
                    continue
                if raw is None:
                    continue
                layers.append((source.name, font_id, raw))
        return layers

    def materialize_texture(self, ref):
        """Resolves a texture ref through the stack and writes it to a colon-free path.

        Returns the on-disk path under work/textures, or None when no layer has it."""
        try:
            namespace, path = split_resource_ref(ref)
        except ValueError as error:
            log(f" → ⚠️ Skipping invalid texture reference '{ref}': {error}")
            return None
        for source in reversed(self.sources):
            data = source.get_texture(namespace, path)
            if data is None:
                continue
            dest = os.path.join(RESOLVED_TEXTURE_DIR, namespace, *path.split("/"))
            root = os.path.realpath(RESOLVED_TEXTURE_DIR)
            if not os.path.realpath(dest).startswith(root + os.sep):
                log(f" → ⚠️ Skipping texture '{ref}' (path escapes the work directory)")
                return None
            try:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, "wb") as f:
                    f.write(data)
            except OSError as error:
                log(f" → ⚠️ Skipping texture '{ref}': {error}")
                return None
            return dest
        return None

    def close(self):
        for source in self.sources:
            try:
                source.close()
            except Exception as error:
                log(f" → ⚠️ Failed to close asset source '{source.name}': {error}")
