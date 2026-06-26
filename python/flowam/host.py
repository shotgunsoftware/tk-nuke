# -
# *****************************************************************************
# Copyright 2026 Autodesk, Inc. All rights reserved.
#
# These coded instructions, statements, and computer programs contain
# unpublished proprietary information written by Autodesk, Inc. and are
# protected by Federal copyright law. They may not be disclosed to third
# parties or copied or duplicated in any form, in whole or in part, without
# the prior written consent of Autodesk, Inc.
# *****************************************************************************
#

import os

from tank import LogManager
from tank.flowam.host import FlowHost
from tank.flowam.utils import search_file_expression
from tank_vendor.flow_integration_sdk.dependency import DependencyData
from tank_vendor.flow_integration_sdk.utils import (
    cleanpath,
    fileext,
    trace,
)
from .flow_write_node.flow_write_node import FlowWriteNode
from .flow_write_node.callbacks import (
    _nuke_flow_write_create,
    _nuke_flow_write_pre_render,
)

import nuke


class NukeHost(FlowHost):
    """Nuke implementation of FlowHost interface.
    This is a collection of required capabilities to support Flow AM integration.
    """

    logger = LogManager.get_logger("NukeHost")

    #: The schema name associated with Nuke workfiles
    WORKFILE_TYPE = "type.workfile.nuke"
    #: Nuke native file types
    FILE_TYPES = ["nk"]
    #: Commonly supported read file types
    COMMON_READ_FILE_TYPES = [
        "ari",
        "arx",
        "avi",
        "bmp",
        "braw",
        "cin",
        "dng",
        "dpx",
        "exr",
        "gif",
        "hdr",
        "jpeg",
        "jpg",
        "mov",
        "mp4",
        "mxf",
        "pic",
        "png",
        "psd",
        "r3d",
        "rgb",
        "rgba",
        "sgi",
        "tga",
        "tif",
        "tiff",
    ]

    def __init__(self, context):

        self.logger.info("Doing NukeHost initialization...")

        super().__init__(context)

        # Detect user modifications in scene and explicitly
        # set the modified flag on scene
        # NOTE: Nuke seems inconsistent with setting this flag
        #       automatically, so adding this guardrail to protect
        #       unsaved changes.
        nuke.addOnUserCreate(self._set_scene_modified)
        nuke.addKnobChanged(self._set_scene_modified)
        nuke.addOnScriptLoad(self._on_script_load)
        nuke.addOnScriptClose(self._on_script_close)

        # Add FlowWrite node to toolbar
        self.logger.info("Adding toolbar commands...")
        nuke.toolbar("Nodes").addCommand(
            "Flow/FlowWrite",
            FlowWriteNode,  # callback to instantiate a write node
            icon="Write.png",
        )

        self.logger.info("Registering global callbacks for Write nodes...")
        nuke.addKnobChanged(FlowWriteNode._on_update_flow_write, nodeClass="Write")
        nuke.addBeforeRender(FlowWriteNode._validate_flow_write, nodeClass="Write")
        nuke.addBeforeRender(FlowWriteNode._pre_render_flow_write, nodeClass="Write")
        nuke.addAfterRender(FlowWriteNode._post_render_flow_write, nodeClass="Write")
        nuke.addOnScriptLoad(FlowWriteNode._register_ui_callback)

        # Add custom Flow integration callbacks for FlowWrite node
        FlowWriteNode.create_callback = _nuke_flow_write_create
        FlowWriteNode.pre_render_callback = _nuke_flow_write_pre_render

    @trace
    def current_file(self) -> str:
        """Return currently opened file in Nuke."""
        return cleanpath(nuke.Root().name())

    @trace
    def new_scene(self, force: bool = False) -> bool:
        """Start new scene in Nuke.

        Args:
            force: If true, force action even if there are unsaved changes.

        Returns:
            True if new scene is opened, False if operation is cancelled.
        """
        # Force new scene
        if force:
            # This option allows you to suppress the unsaved changes dialog
            nuke.scriptSaveAndClear(ignoreUnsavedChanges=True)
            return True
        else:
            # This will check for unsaved changes and automatically
            # prompt the user with an option to save
            # If user chooses to cancel, this will return False
            return nuke.scriptClose()

    @trace
    def open_file(self, file_path: str) -> bool:
        """Open given file path in Nuke.

        Args:
            file_path: Full path to file to be opened.

        Returns:
            True if file is opened, False on error or if operation is cancelled.
        """
        # NOTE: in toolkit, scriptOpen() function seems to be wired to
        #       launch a new instance of Nuke if there are any unsaved
        #       changes in current scene. To circumvent this, we will
        #       clear the scene before opening.
        # NOTE: new_scene() will check unsaved changes and allow the user
        #       to save, not save, or cancel.
        if not self.new_scene():
            return False
        nuke.scriptOpen(file_path)
        # NOTE: the act of opening the file triggers changes which marks
        #       the scene as modified via our callback. Flag the scene
        #       as unmodified post open to avoid confusion.
        self._set_scene_modified(False)
        return True

    @trace
    def save_file(self, file_path: str):
        """Save the current script to the specified file path.

        Args:
            file_path: Absolute local path to save file.

        Raises:
            ValueError
        """
        ext = fileext(file_path)
        if ext not in self.FILE_TYPES:
            raise ValueError(f'Invalid native file extension "{ext}" provided.')

        # Save without overwrite prompt
        nuke.scriptSaveAs(file_path, overwrite=1)

    @trace
    def dialog(
        self,
        title: str,
        msg: str,
        buttons: list[str] | None = None,
        default: int | None = None,
        cancel: int | None = None,
        no_ui_option: int | None = None,
        input_fields: dict | None = None,
    ) -> int:
        """Pop up a dialog in the dcc.

        Args:
            title: Title of dialog window.
            msg: Message to be displayed.
            buttons: List of strings denoting buttons to be added to dialog.
                     NOTE: Maximum of 9 buttons can be supported for this host.
                     If not provided, a default "OK" button will be created.
            default: Index of default button. Default behaviour is to use the second option
                     if available, otherwise the first.
            cancel: Index of cancel button. Default behaviour is to use the first option.
            no_ui_option: If Nuke is running without UI, this option will automatically be returned.
                          If None, use default value.
            input_fields: Dictionary of string keys to default string values.
                          Input text fields will be added to the dialog
                          with labels matching keys. Upon dialog acceptance,
                          the values of the fields will be stored in the
                          same dictionary overwriting the default values
                          provided.

                          NOTE: This is a quick stop-gap solution enabling
                                user input in a nuke dialog (required for
                                FlowWrite publish process). A nicer solution
                                will follow when a custom Nuke dialog is
                                implemented.

        Returns:
            The index of the button selected by user. Value of -1 indicates dismissed dialog.

        Raises:
            ValueError
        """

        # Ensure that we have at least one button
        # and appropriate default/cancel indices
        if not buttons:
            buttons = ["OK"]
        if default is None:
            default = 1 if len(buttons) >= 2 else 0
        if cancel is None:
            cancel = 0
        if default >= len(buttons):
            raise ValueError("Default index provided is out of range.")
        if cancel >= len(buttons):
            raise ValueError("Cancel index provided is out of range.")

        # Ensure that button list is unique, otherwise it will make the
        # mapping at the end of this function difficult.
        if not len(buttons) == len(set(buttons)):
            raise ValueError("Button values must be unique.")

        # Return default option when no UI is available
        if not nuke.GUI:
            return no_ui_option if no_ui_option is not None else default

        # NOTE: nuke automatically wires cancel action to first option
        #       and default action to second option if it exists.
        #       We must renumber the options to respect selected default/cancel
        #       options, but preserve initial order to return accurate result.
        nuke_order = []
        default_opt = cancel_opt = None
        # First we'll add all the non-special actions in order to a list
        # Match the default and cancel options and store them separately
        for i, button in enumerate(buttons):
            if i in [default, cancel]:
                if i == default:
                    default_opt = button
                if i == cancel:
                    cancel_opt = button
                continue
            nuke_order.append(button)
        # Next we will insert the cancel and default actions to the start
        # of the list.
        # NOTE: if these happen to be the same action, they will be added
        # twice, intentionally! This is necessary to support default and cancel
        # option being the same which is commonly desired in many situations where
        # "Cancel" is the safest default action.
        # TODO: need to figure out how to hide the duplicate button in the UI to
        #       avoid confusion, but for now, this is the safest correct implementation!
        nuke_order.insert(0, cancel_opt)  # type: ignore[arg-type]
        nuke_order.insert(1, default_opt)  # type: ignore[arg-type]

        # Create a nuke panel
        panel = nuke.Panel(title)

        # Add message label
        # NOTE: this is not read only unfortunately!
        # TODO: find a better way to display message
        panel.addNotepad("", msg)

        # Add input fields
        if input_fields:
            for field_name, value in input_fields.items():
                panel.addNotepad(field_name, value)

        # Add the buttons in order
        # NOTE: for now, this may result in duplicate buttons if default and cancel
        #       are the same! Ideally we'd want to hide one of them, but can't do that
        #       with current nuke.Panel implementation.
        cancel_and_default_are_same = nuke_order[0] == nuke_order[1] and len(
            nuke_order
        ) > len(buttons)
        for i, button in enumerate(nuke_order):
            panel.addButton(button)
            if i == 1 and cancel_and_default_are_same:
                # TODO: hide button somehow...
                pass

        # Show dialog modally and capture the result
        result = panel.show()
        # Map back result to original order
        value = nuke_order[result]
        mapped_result = buttons.index(value)
        # Retrieve input fields and store values in original dictionary
        if input_fields:
            for field_name in input_fields:
                value = panel.value(field_name)
                input_fields[field_name] = value
        return mapped_result

    @trace
    def file_dialog(
        self,
        title: str,
        starting_dir: str = "",
        folder_mode: bool = False,
        file_type: str = "*",
        multi_select: bool = False,
    ) -> list[str]:
        """Invoke a file dialog for selecting one or more file paths.

        Args:
            title: Title of dialog.
            starting_dir: Starting location of dialog.
            folder_mode: If True, dialog will browse folders instead of files.
            file_type: Extension of file type to filter for.
                         Applicable only when browsing files.
            multi_select: If True, allow multiple selection of files.
                          Applicable only when browsing files.

        Returns:
            A list of file/directory paths.
            If multi_select = False, the return value will be a list of size 1.
            If user cancels, list will be empty.
            If Nuke is running without a GUI, empty list is returned.
        """
        if not nuke.GUI:
            return []

        if starting_dir and not starting_dir.endswith("/"):
            # This will ensure user starts in this directory when they browse
            starting_dir += "/"

        file_filter = "*/" if folder_mode else f"*.{file_type}"
        result = nuke.getFilename(
            title, file_filter, starting_dir, multiple=multi_select
        )
        if result is None:
            return []  # user cancelled

        if not multi_select:
            result = [result]

        return [cleanpath(path) for path in result]

    @trace
    def copy_to_clipboard(self, text: str) -> bool:
        """Copy given text to clipboard.

        Args:
            text: Text to be copied.

        Returns:
            True on success.
        """
        from tank.platform.qt import QtGui

        app = QtGui.QApplication.instance()
        if app:
            app.clipboard().setText(text)
            return True
        return False

    def get_dependency_tree(self, must_exist: bool = True) -> DependencyData:
        """Return a DependencyData object which is the root of the
        dependency tree for the scene.

        Args:
            must_exist: Only return dependencies that can be found on disk.
        """
        dependencies = self._get_nuke_dependencies(must_exist=must_exist)
        dependencies.sort()
        root = DependencyData(dependencies=dependencies)
        for d in dependencies:
            d.parent = root
        return root

    @trace
    def update_dependency(
        self,
        dep: DependencyData,
        file_path: str,
    ) -> DependencyData:
        """Update an existing dependency to point to given file in current script.

        Args:
            dep: DependencyData node which identifies the dependency to be updated.
            file_path: New path to set dependency to.

        Returns:
            DependencyData object describing new state of dependency.
            NOTE: This will be an isolated node, not including sub-dependency info.

        Raises:
            UpdateDependencyError
        """
        node_handle = dep.node_handle
        attribute = dep.attribute

        node = nuke.toNode(node_handle)
        if not node:
            msg = "Error updating dependency. "
            msg += f"Invalid node handle provided: {node_handle}."
            raise RuntimeError(msg)

        knob = node.knob(attribute)
        if not knob:
            msg = "Error updating dependency. "
            msg += f"Invalid knob provided for node [{node_handle}]: {attribute}."
            raise RuntimeError(msg)

        # Set path only if it has changed
        orig_path = cleanpath(knob.value() or "")
        if file_path != orig_path:
            knob.setValue(file_path)

        updated_dep = DependencyData(
            dep_type=dep.dep_type,
            node_handle=dep.node_handle,
            node_type=dep.node_type,
            attribute=dep.attribute,
            file_path=self._resolve_path(file_path),
            raw_path=file_path,
        )

        self.logger.info(
            f'Dependency node "{node_handle}" updated to point to file "{file_path}".'
        )
        return updated_dep

    def env_var_marker(self, var_name: str) -> str:
        """Return the environment variable marker format for Nuke.

        Args:
            var_name: The environment variable name.

        Returns:
            Environment variable marker in TCL format: [getenv VAR_NAME]
        """
        return f"[getenv {var_name}]"

    # ------------------------------------------
    # ADDITIONAL SUBCLASS FUNCTIONS
    # ------------------------------------------

    @trace
    def create_reference(self, file_path: str, namespace: str) -> DependencyData:
        """Create a nuke read node to file.

        Args:
            file_path: Path to be read into Nuke.
            namespace: Namespace to be added to read node.

        Returns:
            DependencyData object with all pertinent info about asset reference created.

        Raises:
            ValueError
        """
        # NOTE: Nuke does not provide a definitive list of extensions that it
        #       supports in its read nodes as of version 16.0.
        #       The best we can do is check the file type against a list of
        #       commonly supported types to block out any obvious outliers.
        ext = fileext(file_path)
        if ext not in self.COMMON_READ_FILE_TYPES:
            msg = f'File type "{ext}" not supported for reading into Nuke.'
            raise ValueError(msg)

        # NOTE: Nuke does not enforce unique names, but to avoid a plethora of
        #       problems we should always avoid duplicate node names, so we
        #       must manually manage unique names.
        node_name = self._get_unique_name(name=namespace)

        # Create the read node in Nuke
        read_node = nuke.nodes.Read(name=node_name, file=file_path)
        msg = f'Read node "{node_name}" created pointing to file "{file_path}".'
        self.logger.info(msg)

        return DependencyData(
            node_handle=node_name,
            node_type=read_node.Class(),
            file_path=self._resolve_path(file_path),
            attribute="file",
            raw_path=file_path,
        )

    def _get_nuke_dependencies(self, must_exist: bool = True) -> list[DependencyData]:
        """Returns all relevant file dependencies in current Nuke script.
        Examples include media reads, and geometry caches.

        Args:
            must_exist: Only return dependencies that can be found on disk.

        Returns:
            List of DependencyData objects containing all pertinent information
            related to a file dependency.
        """

        # NOTE: this initial version (Phase 1) does not deal with gizmos and subdependencies
        #       of gizmos. If there are gizmos present all subdependencies will simply
        #       appear as a flat list with this solution. In the next iteration (Phase 2),
        #       we may consider gizmos as special dependencies that hold sub-dependencies
        #       and build a tree structure this way.

        # Phase 1: External dependency scan for a Nuke script
        # Includes: Read/DeepRead inputs + geometry caches + read-from-file cameras read-from-file
        # Excludes: ALL output paths (Write/DeepWrite/WriteGeo*)
        # Excludes: fonts, luts, ocio configs, gizmos, templates (by using a whitelist approach)

        # Nuke nodes that read from external files
        # We need to filter for these
        INPUT_MEDIA_NODES = {
            "Read",  # regular read node
            "DeepRead",  # read node for deep image formats (eg. exr)
            "ReadOIIO",  # read node using OpenImageIO
        }

        GEO_CACHE_NODES = {
            "ReadGeo2",
            "ReadGeo",  # older
        }

        # Some camera nodes can be set to read from file
        CAMERA_NODES = {
            "Camera2",
            "Camera",
        }

        # Output node classes to exclude entirely
        # Output nodes do not use dependencies, but create biproducts
        OUTPUT_NODES = {
            "Write",
            "DeepWrite",
            "WriteGeo",
            "WriteGeo2",
        }

        deps = []

        # Get list of all dependencies in all containers and nested containers
        # within Nuke script
        for node in nuke.allNodes(recurseGroups=True):
            node_class = node.Class()

            # Exclude outputs entirely
            if node_class in OUTPUT_NODES:
                continue

            # Media reads
            if node_class in INPUT_MEDIA_NODES:
                dep = self._get_dependency_info(node, "file", must_exist)
                if dep:
                    deps.append(dep)

                dep = self._get_dependency_info(node, "proxy", must_exist)
                if dep:
                    deps.append(dep)

            # Geometry cache reads
            elif node_class in GEO_CACHE_NODES:
                dep = self._get_dependency_info(node, "file", must_exist)
                if dep:
                    deps.append(dep)

            # Check for cameras that are read from file
            elif node_class in CAMERA_NODES:
                # Some camera nodes have a "file" knob, and sometimes a "read_from_file" toggle.
                if "read_from_file" in node.knobs():
                    # NOTE: this knob is a Boolean_Knob which always returns a float
                    #       0.0 -> off
                    #       1.0 -> on
                    if node["read_from_file"].value():
                        dep = self._get_dependency_info(node, "file", must_exist)
                        if dep:
                            deps.append(dep)

        return deps

    def _get_dependency_info(self, node, attr, must_exist) -> DependencyData | None:
        """Return DependencyData node with file path information
        of given Nuke node and knob name. If knob or path is not defined,
        return None. If must_exist=True, return None if the path does not
        exist on disk.
        """
        if attr not in node.knobs():
            return None
        raw_path = node[attr].value()
        if not raw_path:
            return None
        # Get resolved file path with env vars replaced
        # and path normalized
        file_path = self._resolve_path(raw_path)
        if must_exist:
            if "%" in file_path:
                # Handle paths with frame padding by searching for matching pattern
                file_list = search_file_expression(file_path)
                if not file_list:
                    self.logger.warning(
                        f"Could not find dependency matching file path: {file_path}"
                    )
                    return None
            elif not os.path.isfile(file_path):
                self.logger.warning(f"Could not find dependency file: {file_path}")
                return None

        # Create a dependency node
        # NOTE: no sub-dependency handling for now
        dep = DependencyData(
            node_handle=node.fullName(),
            node_type=node.Class(),
            attribute=attr,
            file_path=file_path,
            raw_path=raw_path,
        )
        # Determine whether the dependency is an asset
        # or local dependency
        dep.identify_component()
        dep.set_type()
        return dep

    def _tcl_subst(self, s: str) -> str:
        """Expand TCL like [value root.name], [getenv ...], etc."""
        try:
            return nuke.tcl("subst", s)
        except Exception:
            return s

    def _resolve_path(self, raw: str) -> str:
        """Normalize and expand env vars, ~, and TCL substitutions."""
        raw = (raw or "").strip().strip('"').strip("'")
        raw = self._tcl_subst(raw)
        raw = os.path.expandvars(raw)
        raw = os.path.expanduser(raw)
        return cleanpath(raw)

    def _get_unique_name(self, name: str) -> str:
        """Provided a name for a new node, determine
        whether the node already exists and add an index
        to avoid duplication. Nodes are assumed to be top-level.

        e.g. base name = "snow"

             existing nodes:
                - snow
                - snow2

             return value = "snow3"

        NOTE: the assumption that the base name does not include an index.
        """
        # Check if node exists as is
        node = nuke.nodeAtPath(name)
        if node is None:
            return name

        i = 2
        while node is not None:
            unique_name = f"{name}{i}"
            node = nuke.nodeAtPath(unique_name)
            i += 1
        return unique_name

    def _set_scene_modified(self, state: bool = True):
        """Set the modified flag for nuke script explicitly."""
        nuke.root().setModified(state)

    def _on_script_load(self):
        """Callback when script is loaded."""
        file_path = self.current_file()
        self.context.set_flow_context(file_path)

    def _on_script_close(self):
        """Callback when script is closed."""
        self.context.clear_flow_context()
