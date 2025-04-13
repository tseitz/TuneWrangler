import json
import os
from typing import Union
from sqlalchemy.orm.exc import NoResultFound
from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6.smartlist import (
    SmartList,
    Property,
    Operator,
    LogicalOperator,
    left_bitshift,
)

from app import backup_rekordbox_md

db = Rekordbox6Database()

commit = True

created = []


def add_tag_condition_to_smart_playlist(
    condition: str,
    smart_list: SmartList,
    operator: Operator = Operator.CONTAINS,
    condition_type: Property = Property.MYTAG,
):
    try:
        tag = db.get_my_tag(Name=condition).one()
        print(tag.Name)
    except NoResultFound as ex:
        print(f"{ex} -> {condition} not found, exiting")
        return
    # print("Tag ID: ", tag.ID)
    # print("Tag Left Bitshift: ", left_bitshift(int(tag.ID)))
    # print("Tag Right Bitshift: ", right_bitshift(int(tag.ID)))

    smart_list.add_condition(
        condition_type,
        operator,
        left_bitshift(int(tag.ID)),
    )


def add_rating_condition_to_smart_playlist(rating: list[str], smart_list: SmartList):
    smart_list.add_condition(Property.RATING, Operator.IN_RANGE, rating[0], rating[1])


def create_smart_playlist_from_data(
    playlist_name: str,
    logical_operator: LogicalOperator = LogicalOperator.ALL,
    main_conditions: set = set(),
    negative_conditions: set = set(),
    contains: list[str] = [],
    does_not_contain: list[str] = [],
    parent_playlist_id: Union[int, None] = None,
    playlist_type: str = "playlist",
    link: Union[str, None] = None,
    rating: list[str] = [],
    sequence: Union[int, None] = None,
):
    if playlist_type == "folder":
        if link is None:
            raise Exception("link is required for folder")
        # sub_folder = db.get_playlist(
        #     Name=playlist_name, ParentID=parent_playlist_id
        # ).one_or_none()
        # if sub_folder is None:
        #     parent_playlist = db.get_playlist(ID=parent_playlist_id)
        #     sub_folder = db.create_playlist_folder(playlist_name, parent_playlist)
        #     parent_playlist_id = sub_folder.ID

        with open(f"playlist-data/{link}", "r") as json_file:
            data = json.load(json_file)["data"]

            main_conditions.update(contains)
            add_data_to_playlist(data, parent_playlist_id, main_conditions)
            return

    smart_list = SmartList(
        logical_operator=logical_operator,
    )

    for main_condition in main_conditions:
        add_tag_condition_to_smart_playlist(main_condition, smart_list)

    # only apply this for all operator (needs to be fixed for any)
    if logical_operator == LogicalOperator.ALL:
        for negative_condition in negative_conditions:
            add_tag_condition_to_smart_playlist(
                negative_condition, smart_list, Operator.NOT_CONTAINS
            )

    for condition in contains:
        add_tag_condition_to_smart_playlist(condition, smart_list)

    for condition in does_not_contain:
        add_tag_condition_to_smart_playlist(
            condition, smart_list, Operator.NOT_CONTAINS
        )

    if rating:
        add_rating_condition_to_smart_playlist(rating, smart_list)

    playlist_exists = db.get_playlist(
        Name=playlist_name, ParentID=parent_playlist_id
    ).one_or_none()

    if not playlist_exists:
        created.append(playlist_name)
        db.create_smart_playlist(
            playlist_name,
            smart_list=smart_list,
            parent=parent_playlist_id,
            # seq=sequence,
        )


def add_data_to_playlist(
    data,
    default_playlist_id: Union[int, None] = None,
    extra_conditions: set = set(),
    index: Union[int, None] = None,
):
    for category in data:
        # only set index on the original parent
        # index = index if default_playlist_id is None else None
        if index is not None:
            print(f"Setting index for {category['parent']}", index)
        main_conditions = set(category["mainConditions"] + list(extra_conditions))

        if not default_playlist_id:
            default_playlist = db.get_playlist(Name="DaneDubz").one()
        else:
            default_playlist = db.get_playlist(ID=default_playlist_id)
        parent_playlist_id = default_playlist.ID

        if category["parent"]:
            existing_playlist = db.get_playlist(
                Name=category["parent"], ParentID=parent_playlist_id
            ).one_or_none()

            if existing_playlist is None:
                existing_playlist = db.create_playlist_folder(
                    category["parent"], default_playlist, index
                )
            parent_playlist_id = existing_playlist.ID

        for playlist in category["playlists"]:
            print()
            create_smart_playlist_from_data(
                playlist_name=playlist["name"],
                logical_operator=playlist["operator"],
                main_conditions=main_conditions,
                negative_conditions=category.get("negativeConditions", set()),
                contains=playlist.get("contains", []),
                does_not_contain=playlist.get("doesNotContain", []),
                rating=playlist.get("rating", []),
                parent_playlist_id=parent_playlist_id,
                playlist_type=playlist.get("playlistType", None),
                link=playlist.get("link", None),
                sequence=index,
            )


def main():
    # Read JSON file
    folder = "playlist-data"

    for index, filename in enumerate(os.listdir(folder), 0):
        # if filename == "weird.json":
        # if filename.endswith(".json"):  # and filename == "main-party.json":
        file_path = os.path.join(folder, filename)

        if os.path.isdir(file_path):
            continue

        with open(file_path, "r") as json_file:
            data = json.load(json_file)["data"]

        add_data_to_playlist(data, index=index + 1)

    print("Created: ", created)
    if commit is True and len(created) > 0:
        print("\nBacking up library and committing...")
        backup_rekordbox_md()
        db.commit()
        print("Complete!")
    else:
        print("Nothing to commit")


if __name__ == "__main__":
    main()
