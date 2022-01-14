import argparse
import json
import collections
import yaml
import os
import re
import glob
from collections import OrderedDict
import pprint

TrackId = collections.namedtuple("TrackId", ["album", "name"])

def escYamlScalar(string):
    return string.replace('"', '\\"')


def ordered_load_all(stream, Loader=yaml.SafeLoader, object_pairs_hook=OrderedDict):
    class OrderedLoader(Loader):
        pass

    def construct_mapping(loader, node):
        loader.flatten_mapping(node)
        return object_pairs_hook(loader.construct_pairs(node))
    OrderedLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        construct_mapping)
    return yaml.load_all(stream, OrderedLoader)


def ordered_dump_all(data, stream=None, Dumper=yaml.SafeDumper, **kwds):
    class OrderedDumper(Dumper):
        pass

    def _dict_representer(dumper, data):
        return dumper.represent_mapping(
            yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
            data.items())

    OrderedDumper.add_representer(OrderedDict, _dict_representer)

    def _str_presenter(dumper, data):
        if len(data.splitlines()) > 1:  # check for multiline string
            return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
        if len(data) > 80:  # check for multiline string
            return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='>')
        return dumper.represent_scalar('tag:yaml.org,2002:str', data)

    OrderedDumper.add_representer(str, _str_presenter)

    return yaml.dump_all(data, stream, OrderedDumper, **kwds)


def merge_bc_ids(args):
    with open(args.musicjson, "r", encoding="utf-8") as fp:
        tuhc_music = json.load(fp)

    track_ids = {}

    for slug, track in tuhc_music.get("tracks").items():
        # print(track)
        name = track.get("name")
        bcid = track.get("bandcampId")
        if not bcid:
            continue
        for album in track.get("album"):
            id = TrackId(album, name)
            assert not track_ids.get(id)
            track_ids[id] = bcid

    misses = []
    for track in track_ids:
        album_txt_path = os.path.join(args.hsmusicdata, "album", f"{track.album}.txt")
        print(album_txt_path)
        assert os.path.isfile(album_txt_path)
        with open(album_txt_path, "r", encoding="utf-8") as fp:
            txt = fp.read()
        match = re.search(rf"Track: {re.escape(track.name)}\n", txt)
        if match:
            txt = txt.replace(match.group(), f"{match.group()}Bandcamp Id: {track_ids[track]}\n")
            with open(album_txt_path, "w", encoding="utf-8") as fp:
                fp.write(txt)
        else:
            misses.append(track)

    print(misses)


def parse_yaml(args):
    # Todo https://til.simonwillison.net/python/style-yaml-dump

    for txt_path in glob.glob(os.path.join(args.hsmusicdata, "**", "*.txt"), recursive=True):
        # if not txt_path.endswith("perfectly-generic-album.txt"):
        #     continue
        print(txt_path)

        with open(txt_path, "r", encoding="utf-8") as fp:
            txt = fp.read()
        txt = re.sub(  # Section divider
            r"^----+$",
            "---",
            txt, flags=re.MULTILINE
        )
        RE_YLABEL = r'\w[^:\n]+: '
        txt = re.sub(  # Has special character to escape
            rf"^({RE_YLABEL}|- )(.*?(: |\[|\]|\"|\||'|\d:\d).*?)$",
            lambda match: f'{match.group(1)}"{escYamlScalar(match.group(2))}"',
            txt, flags=re.MULTILINE
        )
        txt = re.sub(  # Startswith to escape
            rf"^({RE_YLABEL}|- )((\*|&|>|<|#).+?)$",
            lambda match: f'{match.group(1)}"{escYamlScalar(match.group(2))}"',
            txt, flags=re.MULTILINE
        )
        txt = re.sub(  # Blockquote style text
            r"^(\w[^:\n]+):\s*\n    ",
            r'\g<1>: |\n    ',
            txt, flags=re.MULTILINE
        )
        pathname, __ = os.path.splitext(txt_path)
        with open("tmp.yaml", "w", encoding="utf-8") as fp:
            fp.write(txt)
        # for obj in ordered_load_all(txt):
        #     assert obj
        #     pprint.pprint(obj)
        with open(pathname + ".yaml", "w", encoding="utf-8") as fp:
            # fp.write(txt)
            ordered_dump_all(
                ordered_load_all(txt), fp, 
                encoding="utf-8", indent=4, allow_unicode=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("hsmusicdata", help="Directory of the hsmusic data repository")
    parser.add_argument("musicjson", help="TUHC music.json file")
    parser.add_argument("commands", action="append")
    args = parser.parse_args()

    cmdmap = {
        "merge_bc_ids": merge_bc_ids,
        "parse_yaml": parse_yaml
    }

    for command in args.commands:
        cmdmap[command](args)


if __name__ == "__main__":
    main()
