# Copyright (c) 2026 Autodesk, Inc. All rights reserved.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Autodesk, Inc.

"""
The FlowWrite node is designed to be pipeline/integration agnostic.
This modules contains the callbacks that support our specific Flow integration.
"""

from __future__ import annotations  # needed for python 3.9 support

import os
import nuke

from tank import LogManager
from tank.flowam import create as flow_create
from tank.flowam import utils as flow_utils
from tank_vendor.flow_integration_sdk import sandbox
from tank_vendor.flow_integration_sdk import storage
from tank_vendor.flow_integration_sdk.exceptions import FlowError
from tank_vendor.flow_integration_sdk.objects import FlowAsset


logger = LogManager.get_logger(__name__)


def _nuke_flow_write_create(write_node: nuke.Node) -> None:
    """Custom callback when FlowWrite node in Nuke is created.

    What is done:
        - set default file type to avoid error
        - set source (host) asset id based on current context
        - set default asset name

    Args:
        write_node: Nuke FlowWrite node that triggered callback.

    Raises:
        RuntimeError
    """
    import sgtk

    # Ensure flow host exists
    host = sgtk.platform.current_engine().flow_host
    if host is None:
        nuke.delete(write_node)
        raise RuntimeError("Flow host is not available in current engine.")

    def handle_error(msg, exc=None):
        # Delete write node and show error dialog.
        # On error we want to delete the FlowWrite node created
        # but this seems to prevent an error dialog from popping up
        # via raising an error, so explicitly display an error dialog as well.
        host.dialog(
            title="Error",
            msg=msg,
            buttons=["Ok"],
            default=0,
            cancel=0,
        )
        nuke.delete(write_node)
        if exc:
            raise RuntimeError(msg) from exc
        else:
            raise RuntimeError(msg)

    context_err = "FlowWrite node can only be used by a published asset. "
    context_err += "Please open a published asset first."

    # Set default file type to jpg
    # (The Write node has an empty file type by default which causes an error.)
    write_node["file_type"].setValue("jpg")

    # Set the source asset id
    context = sgtk.platform.current_engine().context
    draft_id = context.flow_draft_id
    if not draft_id:
        # We are not in an asset context
        handle_error(context_err)
        return  # unreachable, but makes control flow clearer

    try:
        asset_id = storage.storage_key_to_asset_id(draft_id)
    except FlowError:
        # This is an unpublished asset
        handle_error(context_err)
        return  # unreachable, but makes control flow clearer

    try:
        asset = FlowAsset(asset_id)
    except Exception as exc:
        # Source asset id is invalid
        msg = f"Failed to obtain host asset. {exc}"
        handle_error(msg, exc)
        return  # unreachable, but makes control flow clearer

    node_name = write_node.name()
    logger.info(
        f'Setting source asset id in FlowWrite node "{node_name}" to: {asset_id}'
    )
    write_node["source_asset_id"].setValue(asset_id)

    # Set default asset name to be that of host asset
    write_node["asset_name"].setValue(asset.name)


def _nuke_flow_write_pre_render(write_node: nuke.Node) -> None:
    """Custom callback executed just before Nuke FlowWrite node runs a render.

    What is done:
        - Find an existing asset to publish to if node doesn't have an asset id set
        - Update the render root of the node
        - Check for existing renders and warn users

    Args:
        write_node: Nuke FlowWrite node that triggered callback.

    Raises:
        RuntimeError
    """
    import sgtk
    from .flow_write_node import FlowWriteNode

    # Ensure flow host exists
    host = sgtk.platform.current_engine().flow_host
    if host is None:
        nuke.delete(write_node)
        raise RuntimeError("Flow host is not available in current engine.")

    asset_id = write_node["asset_id"].value()

    if not asset_id:
        # If no asset id is associated with the node, check based on
        # name matching if there is an existing child of the host asset
        # that would make sense to publish under. If not, assume we are
        # publishing a new asset. Otherwise, ask user if they would like to
        # publish to the existing asset.
        asset_name = write_node["asset_name"].value()
        source_asset = FlowAsset(write_node["source_asset_id"].value())
        existing_asset = source_asset.find_child(asset_name)
        if existing_asset:
            msg = f'An asset name "{asset_name}" already exists under the current '
            msg += "host asset. Would you like to publish to this asset or create "
            msg += "a new one?"
            result = host.dialog(
                title="Asset Name Conflict",
                msg=msg,
                buttons=["Publish to existing", "Create new", "Cancel"],
                default=0,
                cancel=2,
            )
            if result == 0:
                # Set the asset id to the existing asset's id
                write_node["asset_id"].setValue(existing_asset.id)
                asset_id = existing_asset.id
            elif result == 1:
                # Ask for a new (unique) name for the asset
                while existing_asset:
                    msg = f'The current name "{asset_name}" is in conflict with an '
                    msg += "existing asset.  Please choose a new asset name."
                    suggested_name = flow_create.ensure_unique_name(
                        asset_name, source_asset
                    )
                    input_fields = {"Asset Name": suggested_name}
                    result = host.dialog(
                        title="New Asset Name",
                        msg=msg,
                        buttons=["OK", "Cancel"],
                        default=0,
                        cancel=1,
                        input_fields=input_fields,
                    )
                    if result == 1:
                        raise RuntimeError("Render cancelled.")
                    asset_name = input_fields["Asset Name"]
                    existing_asset = source_asset.find_child(asset_name)
                write_node["asset_name"].setValue(asset_name)
            elif result == 2:
                # Cancel render
                raise RuntimeError("Render cancelled.")
            else:
                raise RuntimeError("Invalid action.")

    def update_render_root(folder: str) -> str:
        # Update the render root and re-calculate the output path based on it
        os.makedirs(folder, exist_ok=True)
        write_node["render_root"].setValue(folder)
        FlowWriteNode._generate_output_path(write_node)
        output_path = write_node["file"].value()
        logger.info(f"Setting render path to: {output_path}")
        return output_path

    # Route the output of the write node to the draft folder of the asset
    # whether it is new or existing
    render_root = write_node["render_root"].value()
    output_path = write_node["file"].value()
    if asset_id:
        # If the asset already exists, make sure render root is
        # set to the correct draft folder
        asset = FlowAsset(asset_id)
        draft_id = sandbox.get_draft_id(asset.id)
        draft_folder = sandbox.get_draft_folder(draft_id)
        if render_root != draft_folder:
            output_path = update_render_root(draft_folder)
    elif render_root == "":
        # If it's a new asset, and the render root hasn't been set,
        # create a new draft folder. Otherwise assume the current root is already
        # the draft folder for the new asset.
        draft_id = sandbox.get_draft_id()  # get new draft id
        draft_folder = sandbox.get_draft_folder(draft_id)
        output_path = update_render_root(draft_folder)

    # Check for existing renders
    file_list = flow_utils.search_file_expression(output_path)
    if file_list:
        msg = "The following renders already exist in the destination directory:\n"
        for f in file_list:
            msg += f"{f}\n"
        msg += "\nWould you like to delete these before rendering?\n"
        msg += "\nNOTE: All renders fitting output path descriptor will be included in publish to Flow."
        result = host.dialog(
            title="Existing renders detected",
            msg=msg,
            buttons=["Yes", "No", "Cancel"],
            default=1,  # by default don't delete
            cancel=2,
        )
        if result == 0:
            # Delete existing renders
            for f in file_list:
                try:
                    logger.info(f"Deleting {f}")
                    os.remove(f)
                except Exception as exc:
                    msg = f'Error trying to delete "{f}": {exc}'
                    raise RuntimeError(msg) from exc
        elif result == 1:
            # Do nothing
            pass
        elif result == 2:
            # Cancel render
            raise RuntimeError("Render cancelled.")
        else:
            raise RuntimeError("Invalid action.")
