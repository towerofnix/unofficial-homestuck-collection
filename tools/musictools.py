import argparse
import json
import collections
import yaml
import os
import re
import glob
import collections
from collections import OrderedDict
import functools
import pprint
import tqdm

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
        TAG_STR = 'tag:yaml.org,2002:str'
        out = None
        if len(data.splitlines()) > 1:  # check for multiline string
            # TODO: Sometimes this style still outputs full lines: see jailbreak commentary for example
            out = dumper.represent_scalar(TAG_STR, data, style='|')
        elif len(data) > 120:  # check for multiline string
            out = dumper.represent_scalar(TAG_STR, data, style='>')
        if re.match(r'^0\d', data):  # Avoid ambigious octal/hex output
            return dumper.represent_scalar(TAG_STR, data, style="'")
        
        out = out or dumper.represent_scalar(TAG_STR, data)
        # print(len(data), len(data.splitlines()), data.splitlines(), ".", out)
        return out

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


def yaml_lint(args):
    for yaml_path in glob.glob(os.path.join(args.hsmusicdata, "**", "*.yaml"), recursive=True):
        with open(yaml_path, "r", encoding="utf-8") as fp:
            this = list(ordered_load_all(fp))
        this = clean_hsmusic_data(this)
        with open(yaml_path, "w", encoding="utf-8") as fp:
            ordered_dump_all(
                this, fp,
                encoding="utf-8", indent=4, allow_unicode=True
            )


def list_keys(args):
    all_keys = collections.Counter()
    # all_keys_set = set()
    for yaml_path in glob.glob(os.path.join(args.hsmusicdata, "**", "*.yaml"), recursive=True):
        with open(yaml_path, "r", encoding="utf-8") as fp:
            for section in ordered_load_all(fp):
                all_keys += collections.Counter(section.keys())
                # all_keys_set |= set(section.keys())
    # pprint.pprint(all_keys_set)
    # pprint.pprint(sorted(all_keys.items()))
    pprint.pprint(all_keys)


def clean_hsmusic_data(sections):
    def coerces_to(type_):
        def decorator_coerce(coerce_):
            @functools.wraps(coerce_)
            def wrapper_coerce(value):
                if isinstance(value, type_):
                    # Value is already an instance of type
                    return value
                try:
                    return coerce_(value)
                except Exception as error:
                    print(f"Coerce error: {value} ({type(value).__name__}) -> {type(type_).__name__} raised {type(error).__name__}")
                    raise error
            return wrapper_coerce
        return decorator_coerce

    @coerces_to(list)
    def listify(obj):
        if isinstance(obj, str) and obj.lower() == "none":
            return []
        else:
            return obj.split(", ")

    @coerces_to(int)
    def intify(obj):
        return int(obj)

    # 0. Special cases happen (has track art)

    key_renames = [
        # 1. All these keys get renamed
        ("Track Art", "Cover Artists"),
        ("Wallpaper Art", "Wallpaper Artists"),
        ("ReferenceS", "Referenced Tracks"),
        ("References", "Referenced Tracks"),
        ("Referenes", "Referenced Tracks"),
        ("Refrences", "Referenced Tracks"),
        ("Samples", "Sampled Tracks"),
        # ("Group", "Groups"),
        ("Duratoin", "Duration"),
        ("Commrntary", "Commentary"),
        # ("Artist", "Artists"),
        ("Banner Art", "Banner Artists"),
        ("Cover Art", "Cover Artists"),
        ("ACT", "Act"),
        ("AKA", "Originally Released As"),
        ("Body", "Content"),
        ("Footer", "Footer Content"),
        ("Listed", "Show in Navigation Bar"),
        ("Note", "Context Notes"),
        ("Original Date", "Date First Released"),
        ("Sidebar", "Sidebar Content"),
        ("Tracks", "Featured Tracks"),
        ("Track Art Date", "Default Track Cover Art Date"),
        ("Commnentary", "Commentary")
    ]

    key_type_coerce = [
        # 2. Then these keys become lists
        (list, listify, [
            "Actions",
            "Albums",
            "Also Released As",
            "Art Tags",
            "Artists",
            "Banner Artists",
            "Contributors",
            "Cover Artists",
            "Default Track Cover Artists",
            "Featured Tracks",
            "Groups",
            # "Group",
            "Referenced Tracks",
            # "References",
            "Sampled Tracks",
            "Tracks",
            "URLs",
            "Wallpaper Artists",
            # "Track Art",
            # "Wallpaper Art",
        ]),

        # 2a. Also these become ints
        (int, intify, [
            "Count"
        ])
    ]

    keyorder = [
        'Name',
        'Album',
        'Track',
        'Directory',
        'Also Released As',
        'Originally Released As',

        'Artist',
        'Artists',
        'Aliases',
        'Contributors',

        'Date',
        'Date First Released',
        'Date Added',

        'Duration',

        'Has URLs',
        'URLs',
        'Dead URLs',

        'Has Track Art',
        'Has Cover Art',
        'Cover Artists',
        'Default Track Cover Artists',
        'Cover Art Date',
        'Cover Art File Extension',

        'Color',
        'Groups',
        'Art Tags',
        'Tag',

        'Referenced Tracks',
        'Sampled Tracks',

        'Lyrics',
        'Commentary',
        'Description',
        'Context Notes',

        'Banner Artists',
        'Banner Dimensions',
        'Banner File Extension',
        'Wallpaper Artists',
        'Wallpaper Style',
        'Wallpaper File Extension',

        'Featured Tracks',
        'Flash',
        'Page',
        'Act',
        'CW',
        # 'Content',
        # 'Listed on Homepage',
        # 'Jump',
        # 'Artists',
        # 'Category',
        # 'Default Track Cover Art Date',
        # 'Row',
        # 'Type',
        # 'Count',
        # 'Actions',
        # 'Jump Color',
        # 'Short Name',
        # 'Major Release',
        # 'Banner Style',
        # 'Homepage',
        # 'Sidebar Content',
        # 'Albums',
        # 'Style',
        # 'Show in Navigation Bar',
        # 'Canonical Base',
        # 'Enable Artist Avatars',
        # 'Enable Flashes & Games',
        # 'Enable Listings',
        # 'Enable News',
        # 'Enable Art Tag UI',
        # 'Enable Group UI',
        # 'Footer Content',
        # 'Commnentary',
        # 'Credits',
        # 'Canon',
    ]

    for i, section in enumerate(sections):
        # Special cases
        if i == 0:  # Album meta
            if section.get("Cover Art"):
                assert not section.get("Cover Artists")
                section["Cover Artists"] = section.pop("Cover Art")
            if section.get("Track Art"):
                assert not section.get("Album Art")
                section["Default Track Cover Artists"] = section.pop("Track Art")
        else:  # Track meta
            if section.get("Track Art"):
                assert not section.get("Cover Artists")
                section["Cover Artists"] = section.pop("Track Art")

        if section.get("Default Track Cover Artists") == "none":
            section["Has Track Art"] = False
            section.pop("Default Track Cover Artists")
        if section.get("Cover Artists") == "none":
            section["Has Cover Art"] = False
            section.pop("Cover Artists")
        if section.get("Jiff") == "Yeah":
            section["Cover Art File Extension"] = "gif"
            section.pop("Jiff")
        if section.get("CW"):
            section["Tag"] = section.pop("CW")
            section["Is CW"] = True

        if section.get("Artist"):
            if section.get("Album") or section.get("Track"):
                assert not section.get("Artists")
                section["Artists"] = section.pop("Artist")

        # Remap keys
        for keya, keyb in key_renames:
            if keya in section:
                assert not section.get(keyb)
                # print(f"RENAME {keyb=} = {keya=} {section.get(keya)=}")
                section[keyb] = section.pop(keya)

        # Coerce types
        for type_, coerce_, key_list in key_type_coerce:
            for key in key_list:
                if section.get(key):
                    current = section[key]
                    # if section.get(key):
                    #     print(f"Section already has key {key!r} {section.get(key)=} {current=}")
                    try:
                        section[key] = coerce_(current)
                    except Exception as error:
                        print(f"Coerce error: COERCE {key=} = {current=} {coerce_(current)=} in {section}")
                        raise

        for key in keyorder[::-1]:
            if key in section:
                section.move_to_end(key, last=False)

    return sections


def restructure_hsmusic_artists(sections):
    artists = {}
    # pprint.pprint(sections)

    deferred = []

    for section in sections:
        if section.get("Alias"):
            deferred.append(section)
        else:
            key = section.pop("Artist")
            assert key
            assert key not in artists
            artists[key] = section

    # pprint.pprint(artists)

    for section in deferred:
        key = section.get("Alias")
        artists[key]['Aliases'] = artists[key].get('Aliases', []) + [section.get("Artist")]
        # artists[key].move_to_end('Artist', last=False)

    # pprint.pprint(artists)

    # return [
    #     {
    #         "Artist": str(key),
    #         **value
    #     }
    #     for key, value in artists.items()
    # ]

    return sorted([
        OrderedDict([
            ("Artist", str(key)),
            *[(k, v) for k, v in sorted(value.items())]
        ])
        for key, value in artists.items()
    ], key=lambda a: a.get("Artist"))


def hsmtxt_to_yaml(args):
    for txt_path in glob.glob(os.path.join(args.hsmusicdata, "**", "*.txt"), recursive=True):
        # if not txt_path.endswith("artists.txt"):
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
            rf"^({RE_YLABEL}|- )((([0-9_]+$)|Yes|[Nn]ull|\*|&|>|<|#).*?)$",
            lambda match: f"{match.group(1)}'{escYamlScalar(match.group(2))}'",
            txt, flags=re.MULTILINE
        )
        txt = re.sub(  # Blockquote style text
            r"^(\w[^:\n]+):\s*\n    ",
            r'\g<1>: |-\n    ',
            txt, flags=re.MULTILINE
        )
        pathname, __ = os.path.splitext(txt_path)
        # with open(pathname + ".txt.yaml", "w", encoding="utf-8") as fp:
        #     fp.write(txt)
        # for obj in ordered_load_all(txt):
        #     assert obj
        #     pprint.pprint(obj)

        sections = clean_hsmusic_data(list(ordered_load_all(txt)))
        if txt_path.endswith("artists.txt"):
            sections = restructure_hsmusic_artists(sections)

        with open(pathname + ".yaml", "w", encoding="utf-8") as fp:
            # fp.write(txt)
            ordered_dump_all(
                sections, fp,
                encoding="utf-8", indent=4, allow_unicode=True)


def diff_yaml_to_out(args):
    # Todo https://til.simonwillison.net/python/style-yaml-dump
    with open(args.outjson, "r", encoding="utf-8") as fp:
        outdata = json.load(fp)

    outdata_albums = {
        a.get("directory"): a
        for a in outdata.get("albumData")
    }

    for txt_path in glob.glob(os.path.join(args.hsmusicdata, "album", "*.yaml"), recursive=True):
        path, filename = os.path.split(txt_path)
        directory, __ = os.path.splitext(filename)
        with open(txt_path, "r", encoding="utf-8") as fp:
            this_album_yaml = list(ordered_load_all(fp))

        outdata_album = outdata_albums.get(directory)
        with open("tmp.yaml", "w", encoding="utf-8") as fp:
            ordered_dump_all([outdata_album], fp)

        albummeta, *tracks = this_album_yaml
        # pprint.pprint(albummeta)
        # pprint.pprint(tracks)

        for infield, outfield in [
            ("Album", "name"),
            ("URLs", "urls")
        ]:
            if albummeta[infield] != outdata_album[outfield]:
                print(f"{infield} {albummeta[infield]=} != {outfield} {outdata_album[outfield]=}")
            else:
                pass
                # print(f"{infield} {albummeta[infield]=} ok {outfield} {outdata_album[outfield]=}")

        break


def main():
    cmdmap = {
        "merge_bc_ids": merge_bc_ids,
        "hsmtxt_to_yaml": hsmtxt_to_yaml,
        "diff_yaml_to_out": diff_yaml_to_out,
        "yaml_lint": yaml_lint,
        "list_keys": list_keys
    }

    parser = argparse.ArgumentParser()
    parser.add_argument("--hsmusicdata", help="Directory of the hsmusic data repository")
    parser.add_argument("--musicjson", help="TUHC music.json file")
    parser.add_argument("--outjson", help="hsmusic data.json file")
    parser.add_argument("commands", nargs='+', choices=cmdmap.keys())   
    args = parser.parse_args()


    for command in args.commands:
        cmdmap[command](args)


if __name__ == "__main__":
    main()
