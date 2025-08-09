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

from rekordbox_backup import backup_rekordbox_db

db = Rekordbox6Database()


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


def add_date_created_condition_to_smart_playlist(
    time_period: int,
    time_unit: str,
    smart_list: SmartList,
    operator: Operator = Operator.IN_LAST,
):
    """
    Add a date created condition to smart playlist.

    Parameters:
    - time_period: Number of time units (e.g., 1, 2, 30)
    - time_unit: Unit of time ('days', 'months', 'years')
    - smart_list: The SmartList object to add condition to
    - operator: The operator to use (default: IN_LAST)
    """
    smart_list.add_condition(
        Property.DATE_CREATED, operator, str(time_period), unit=time_unit
    )


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
    date_created: Union[dict, None] = None,
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
            # TODO: needs to log created from here
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

    if date_created:
        add_date_created_condition_to_smart_playlist(
            time_period=date_created.get("time_period", 1),
            time_unit=date_created.get("time_unit", "months"),
            smart_list=smart_list,
            operator=(
                Operator.IN_LAST
                if date_created.get("operator") == "IN_LAST"
                else Operator.IN_LAST
            ),
        )

    playlist_exists = db.get_playlist(
        Name=playlist_name, ParentID=parent_playlist_id
    ).one_or_none()

    if not playlist_exists:
        db.create_smart_playlist(
            playlist_name,
            smart_list=smart_list,
            parent=parent_playlist_id,
            # seq=sequence,
        )
        return playlist_name


def add_data_to_playlist(
    data,
    default_playlist_id: Union[int, None] = None,
    extra_conditions: set = set(),
    index: Union[int, None] = None,
    created: list[str] = [],
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
            playlist_created = create_smart_playlist_from_data(
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
                date_created=playlist.get("dateCreated", None),
            )
            if playlist_created:
                created.append(playlist_created)

    return created


def main():
    # Read JSON file
    folder = "playlist-data"
    commit = True
    created = []

    if commit is True:
        print("\nCommit is True, backing up library...")
        backup_rekordbox_db()

    for index, filename in enumerate(sorted(os.listdir(folder)), 0):
        # if filename == "crispy-speakers.json":
        # if index < 5:
        #     continue

        file_path = os.path.join(folder, filename)

        if os.path.isdir(file_path):
            continue

        with open(file_path, "r") as json_file:
            data = json.load(json_file)["data"]

        created = add_data_to_playlist(data, index=index + 1, created=created)

        print("Created: ", created)
        if commit is True and len(created) > 0:
            print(f"\nCommitting {data[0]['parent']} playlist...")
            db.commit()
            print("Committed")
            created = []

    print("\nComplete!")


if __name__ == "__main__":
    main()
