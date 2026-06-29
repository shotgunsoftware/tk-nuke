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
FlowWrite node definition for Nuke.
"""

from __future__ import annotations  # needed for python 3.9 support

import nuke

from tank import LogManager
from tank.flowam import utils as flow_utils
from tank_vendor.flow_integration_sdk.utils import cleanpath


class FlowWriteNode:
    """Factory and callback host for FlowWrite nodes in Nuke.

    A FlowWrite node is a standard Nuke Write node augmented with a "Flow"
    tab that carries asset management metadata. Output paths are computed
    automatically from the asset name and file type knobs - users cannot
    edit the ``file`` knob directly.

    Publish business logic is injected externally via the class-level
    callback slots below.

    Callback contract:
        Each callback receives a single ``nuke.Node`` argument for the
        FlowWrite node that triggered the event.

        - ``create_callback(node)``     - called once when node is created.
        - ``validate_callback(node)``   - before each render; raise to abort.
        - ``pre_render_callback(node)`` - called after validation, before render.
        - ``post_render_callback(node)``- called after each successful render.
    """

    logger = LogManager.get_logger("FlowWriteNode")

    # Knob which designates node as FlowWrite node
    FLOW_WRITE_KNOB = "flow_write"

    # ------------------------------------------------------------------
    # Class-level callback slots
    # ------------------------------------------------------------------

    #: Called once when a new FlowWrite node is created.
    create_callback = None
    #: Called before each render to validate node state; raise to abort.
    validate_callback = None
    #: Called after validation, immediately before the render starts.
    pre_render_callback = None
    #: Called after each successful render completes.
    post_render_callback = None

    # ------------------------------------------------------------------
    # File type helpers
    # ------------------------------------------------------------------

    #: Maps file_type names to actual file extensions where they differ.
    FILE_TYPE_TO_EXT: dict[str, str] = {
        "jpeg": "jpg",
        "tiff": "tif",
        "targa": "tga",
        "mpeg": "mpg",
    }

    #: File types that produce a single movie file rather than per-frame images.
    MOVIE_FILE_TYPES: list[str] = ["mov", "avi", "mpeg", "mpg", "mp4"]

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, name: str = "FlowWrite") -> None:
        """Create a FlowWrite node.

        Instantiating this class is the toolbar command registered by the app.
        Nuke calls it with no arguments when the user clicks the menu item.

        Args:
            name: Base name for the new node. Nuke will append a numeric
                  suffix if a node with this name already exists.
        """
        write_node = nuke.createNode("Write", inpanel=False)
        write_node.setName(name, uncollide=True)

        # Make modifications to original knobs
        self._modify_write_node(write_node)

        # Add custom Flow tab with pertinent settings
        self._add_flow_knobs(write_node)

        if FlowWriteNode.create_callback:
            FlowWriteNode.create_callback(write_node)

        self.node = write_node

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @classmethod
    def is_flow_write(cls, node: nuke.Node):
        """Return True if given node is a FlowWrite node."""
        return cls.FLOW_WRITE_KNOB in node.knobs()

    @classmethod
    def get_flow_write_nodes(cls) -> list[nuke.Node]:
        """Return all FlowWrite nodes present in the current Nuke script.

        Returns:
            Write-class nuke nodes that carry the ``flow_write`` marker knob.
        """
        return [
            node
            for node in nuke.allNodes("Write")
            if cls.FLOW_WRITE_KNOB in node.knobs()
        ]

    @classmethod
    def get_node_render_files(cls, write_node: nuke.Node) -> list[str]:
        """Return the list of rendered files for the node."""

        if not cls.is_flow_write(write_node):
            raise RuntimeError("Input node is not a FlowWrite node.")

        render_path = write_node["file"].value()
        renders = flow_utils.search_file_expression(render_path)
        for r in renders:
            cls.logger.info(f"render: {r}")
        return renders

    @classmethod
    def get_asset_name(cls, write_node: nuke.Node) -> str:
        """Return asset name set on node."""

        if not cls.is_flow_write(write_node):
            raise RuntimeError("Input node is not a FlowWrite node.")

        k_asset_name = write_node.knobs()["asset_name"]
        return k_asset_name.value()

    # ------------------------------------------------------------------
    # Node setup helpers
    # ------------------------------------------------------------------

    @classmethod
    def _modify_write_node(cls, write_node: nuke.Node) -> None:
        """Adjust the built-in Write node knobs for FlowWrite behaviour.

        Args:
            write_node: The Nuke Write node to modify.
        """

        # Hide native knobs that are not applicable
        to_hide = ["proxy"]
        for knob in to_hide:
            if knob in write_node.knobs():
                write_node[knob].setVisible(False)

        # Disable native knobs that we don't want edited directly
        to_disable = ["file"]
        for knob in to_disable:
            if knob in write_node.knobs():
                write_node[knob].setEnabled(False)

        # Add tooltip to file knob
        if "file" in write_node.knobs():
            write_node["file"].setTooltip(
                "The file path will be generated using the asset name and frame pad "
                "information in the Flow tab, as well as the file type set."
            )

    @classmethod
    def _add_flow_knobs(cls, write_node: nuke.Node) -> None:
        """Add the Flow tab and all custom knobs to the write node.

        Args:
            write_node: The Nuke Write node to augment.
        """
        write_node.addKnob(nuke.Tab_Knob("flow", "Flow"))

        # Hidden flow indicator knob
        k_flow = nuke.Boolean_Knob(cls.FLOW_WRITE_KNOB)
        k_flow.setVisible(False)
        k_flow.setEnabled(False)
        k_flow.setValue(True)
        write_node.addKnob(k_flow)

        # Hidden root dir property knob
        k_root = nuke.String_Knob("render_root")
        k_root.setVisible(False)
        k_root.setEnabled(False)
        write_node.addKnob(k_root)

        write_node.addKnob(nuke.Text_Knob("", ""))  # add separator
        # Asset name knob
        k_asset_name = nuke.String_Knob("asset_name", "Asset Name")
        k_asset_name.setTooltip(
            "Name of the Flow asset. Also used as the base file name for renders."
        )
        write_node.addKnob(k_asset_name)
        # Description knob
        k_desc = nuke.String_Knob("description", "Description")
        k_desc.setTooltip(
            "A description of the asset. This lives on the asset and can be "
            "modified throughout its lifetime."
        )
        write_node.addKnob(k_desc)

        write_node.addKnob(nuke.Text_Knob("", ""))  # add separator
        # Indicate whether frame padding should be included in file name
        k_use_fp = nuke.Boolean_Knob("use_frame_padding", "Use frame padding")
        k_use_fp.setTooltip("Include frame padding in the export path.")
        k_use_fp.setValue(False)
        write_node.addKnob(k_use_fp)
        # Frame pad length knob
        k_fp = nuke.Int_Knob("frame_pad", "Frame Pad")
        k_fp.setTooltip("Number of digits in frame padding.")
        k_fp.setRange(1, 6)
        k_fp.setValue(4)
        write_node.addKnob(k_fp)

        write_node.addKnob(nuke.Text_Knob("", ""))  # add separator
        # Non-editable asset id knob - will remain unset until asset is published
        k_asset_id = nuke.String_Knob("asset_id", "Asset Id")
        k_asset_id.setEnabled(False)
        k_asset_id.setTooltip("Flow asset id associated with this FlowWrite node.")
        write_node.addKnob(k_asset_id)

        # Non-editable source asset id knob - the host asset of the FlowWrite node
        # This should be set by the create callback
        k_source_id = nuke.String_Knob("source_asset_id", "Source Asset")
        k_source_id.setEnabled(False)
        k_source_id.setTooltip(
            "Flow asset id of the Nuke script asset that hosts " "this FlowWrite node."
        )
        write_node.addKnob(k_source_id)

    # ------------------------------------------------------------------
    # Output path computation
    # ------------------------------------------------------------------

    @classmethod
    def _generate_output_path(cls, write_node: nuke.Node) -> None:
        """Recompute and set the ``file`` knob from current node settings.

        Args:
            write_node: The FlowWrite node whose output path should be updated.
        """
        asset_name = write_node["asset_name"].value()
        use_frame_padding = write_node["use_frame_padding"].value()
        # Nuke returns int knobs as floats so explicitly cast to an int
        frame_pad = int(write_node["frame_pad"].value())
        file_type = write_node["file_type"].value()
        render_root = write_node["render_root"].value()
        # Determine file name
        ext = cls.FILE_TYPE_TO_EXT.get(file_type, file_type)
        if use_frame_padding and ext not in cls.MOVIE_FILE_TYPES:
            filename = f"{asset_name}.%0{frame_pad}d.{ext}"
        else:
            filename = f"{asset_name}.{ext}"
        file_path = cleanpath(render_root, filename)
        # Set output path
        write_node["file"].setValue(file_path)

    # ------------------------------------------------------------------
    # Nuke global callbacks
    # (Registered/deregistered by app.py via nuke.add*/nuke.remove*)
    # ------------------------------------------------------------------

    @classmethod
    def _on_update_flow_write(cls) -> None:
        """``knobChanged`` callback - recompute the output path when relevant
        knobs change on a FlowWrite node.
        """

        # Retrieve current node context
        write_node = nuke.thisNode()
        knob = nuke.thisKnob()

        if not cls.is_flow_write(write_node):
            return  # This is not a flow write node

        # List of properties which affect the file path property
        file_path_drivers = (
            "asset_name",
            "file_type",
            "frame_pad",
            "render_root",
            "use_frame_padding",
        )
        if knob.name() in file_path_drivers:
            # Recompute file path
            cls._generate_output_path(write_node)

    @classmethod
    def _validate_flow_write(cls) -> None:
        """``beforeRender`` callback - validate required knobs before allowing
        the render to proceed.

        Raises:
            RuntimeError: If a required knob is missing, aborting the render.
        """
        # Get current node context
        write_node = nuke.thisNode()

        if not cls.is_flow_write(write_node):
            return  # This is not a flow write node

        # Check for mandatory properties
        if not write_node["asset_name"].value().strip():
            nuke.message("Asset Name must be set.")
            raise RuntimeError("Missing required knob: asset_name")

        if not write_node["file_type"].value().strip():
            nuke.message("File Type must be set.")
            raise RuntimeError("Missing required knob: file_type")

        if not write_node["source_asset_id"].value().strip():
            nuke.message("Source asset id must be set.")
            raise RuntimeError("Missing required knob: source_asset_id")

        if cls.validate_callback:
            cls.validate_callback(write_node)

    @classmethod
    def _pre_render_flow_write(cls) -> None:
        """``beforeRender`` callback - runs after validation, immediately
        before the render starts.
        """
        # Get current node context
        write_node = nuke.thisNode()

        if not cls.is_flow_write(write_node):
            return  # This is not a flow write node

        # Run custom post render callback
        if cls.pre_render_callback:
            cls.pre_render_callback(write_node)

    @classmethod
    def _post_render_flow_write(cls) -> None:
        """``afterRender`` callback — triggers the Flow publish."""

        # Get current node context
        write_node = nuke.thisNode()

        if not cls.is_flow_write(write_node):
            return  # This is not a flow write node

        # Run custom post render callback
        if cls.post_render_callback:
            cls.post_render_callback(write_node)

    # ------------------------------------------------------------------
    # Script-load knob persistence
    # ------------------------------------------------------------------

    @classmethod
    def _register_ui_callback(cls) -> None:
        """``onScriptLoad`` callback - registers a one-shot ``updateUI``
        callback that re-applies knob settings which Nuke does not persist
        across save/reload (e.g. ``setEnabled``, ``setVisible``).

        More info:

        Triggered on script load, this callback will register
        an update ui callback which will then get deregistered after first execution.

        Explanation:

        Nuke Write node default knob settings are not stored with the script. Instead,
        they are re-applied post script load. Since the FlowWrite nodes disable and hide
        some knobs, we want to persist this behaviour after a script is re-opened.
        The only effective time to do this is in an "update ui" callback, but we only
        really need it to be run once after a script is opened. The solution is to have the
        "script load" callback register the "update ui" callback. But since the update ui callback
        is run with high frequency, we want to deregister this callback as soon as it's run once.
        So the callback itself will unregister itself.
        """
        nuke.addUpdateUI(cls._apply_knob_settings, nodeClass="Write")

    @classmethod
    def _apply_knob_settings(cls) -> None:
        """Re-apply non-persistent knob settings to all FlowWrite nodes.

        Deregisters itself after the first execution so it only runs once
        per script load.
        """
        for write_node in nuke.allNodes("Write"):
            if not cls.is_flow_write(write_node):
                cls._modify_write_node(write_node)

        nuke.removeUpdateUI(cls._apply_knob_settings)
