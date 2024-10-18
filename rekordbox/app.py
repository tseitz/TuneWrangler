import shutil
import os
import xml.etree.ElementTree as ET
from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6.smartlist import SmartList

db = Rekordbox6Database()

# for content in db.get_content():
#     print(content.Title, content.Artist.Name)

# tags = db.get_my_tag()
# for tag in tags:
#     print(f"{tag.Name} -> {tag.ID} -> {tag.ParentID}")


def copy_smart_playlist_from(
    db: Rekordbox6Database,
    playlist_name: str,
    new_name: str,
    smart_list,
    parent_id: str = "0",
):
    base_playlist = db.get_playlist(Name=playlist_name).one()
    smart_list = SmartList(
        logical_operator=smart_list.get("LogicalOperator"),
        auto_update=smart_list.get("AutomaticUpdate"),
    )
    # smart_list.conditions = base_playlist.SmartList
    smart_list.parse(base_playlist.SmartList)
    playlist = db.create_smart_playlist(
        new_name,
        smart_list=smart_list,
        parent=parent_id,
        # seq=base_playlist.Seq + 1, will automatically insert at end
    )


def main():
    playlists = db.get_playlist()
    for playlist in playlists:
        if playlist.is_smart_playlist:
            root = ET.fromstring(playlist.SmartList)

            # print(dict(playlist))
            if playlist.ParentID != "0":
                print(f"{playlist.Parent.Name} -> {playlist.Name}")
            else:
                print(f"{playlist.Name}")

            if "Dub Categorize" in playlist.Name:
                print(playlist.Name)
            if playlist.Name == "Dub Categorize":
                print("hello!")
                copy_smart_playlist_from(
                    db,
                    playlist.Name,
                    f"Copy of {playlist.Name}",
                    smart_list=root,
                    parent_id=playlist.ParentID,
                )
            else:
                continue

            for condition in root.findall("CONDITION"):
                print()
                property_name = condition.get("PropertyName")
                if property_name == "myTag":
                    value_left = int(condition.get("ValueLeft"))
                    value_right = condition.get("ValueRight")
                    if value_right != "":
                        print("Found a value right", value_right, playlist.Name)
                    if int(value_left) < 0:
                        # Add 2^32 to the negative number to convert it
                        value_left = value_left + 2**32
                    print(
                        value_left,
                        "all" if root.get("LogicalOperator") == "1" else "any",
                    )
                    tag = db.get_my_tag(ID=str(value_left))
                    if tag is None:
                        print(f"Can't find tag for {playlist.Name} {value_left}")
                        break
                    print(f"is {tag.Name}")
                print("done")


# smart playlist xml
# <NODE Id="123456789" LogicalOperator="1" AutomaticUpdate="1">
# 1 = all
# 2 = any
# <CONDITION Tag="123456789" Operator="1" ValueLeft="-1234>
# 1 =


# create playlist
# playlist = db.create_playlist("My Playlist")
# order it
# playlist = db.create_playlist("My Playlist", seq=2)

# add playlist to folder
# folder = db.get_playlist(Name="My Folder").one()  # Query for unique playlist folder
# playlist = db.create_playlist("My Playlist", parent=folder)


def add_to_playlist(db, playlist, content):
    content = db.get_content(ID=0)
    playlist = db.get_playlist(Name="My Playlist").one()
    song = db.add_to_playlist(playlist, content)


def remove_from_playlist(db, playlist, content):
    playlist = db.get_playlist(Name="My Playlist").one()
    song = playlist.Songs[0]

    db.remove_from_playlist(playlist, song)


def backup_rekordbox_md():
    db_source = "/Users/tseitz/Library/Application Support/Pioneer"
    db_destination = "/Users/tseitz/Dropbox/DJ/SlimChance DJ Music/Rekordbox DB Backup/Application Support"

    lib_source = "/Users/tseitz/Library/Pioneer"
    lib_destination = (
        "/Users/tseitz/Dropbox/DJ/SlimChance DJ Music/Rekordbox DB Backup/Library"
    )

    if not os.path.exists(db_destination):
        os.makedirs(db_destination)
    else:
        shutil.rmtree(db_destination)

    if not os.path.exists(lib_destination):
        os.makedirs(lib_destination)
    else:
        shutil.rmtree(lib_destination)

    shutil.make_archive(
        os.path.join(db_destination, "rekordbox_backup"), "zip", db_source
    )
    shutil.make_archive(
        os.path.join(lib_destination, "rekordbox_backup"), "zip", lib_source
    )


# folders = []

if __name__ == "__main__":
    main()
