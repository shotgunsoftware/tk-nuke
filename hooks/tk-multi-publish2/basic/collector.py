# Copyright (c) 2017 Shotgun Software Inc.
# 
# CONFIDENTIAL AND PROPRIETARY
# 
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit 
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your 
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights 
# not expressly granted therein are reserved by Shotgun Software Inc.

import os
import nuke
import sgtk

HookBaseClass = sgtk.get_hook_baseclass()

# A look up of node types to parameters for finding outputs to publish
_NUKE_OUTPUTS = {
    "Write": "file",
    "WriteGeo": "file",
}


class NukeSessionCollector(HookBaseClass):
    """
    Collector that operates on the current nuke/nukestudio session. Should
    inherit from the basic collector hook.
    """

    @property
    def settings(self):
        """
        Dictionary defining the settings that this collector expects to receive
        through the settings parameter in the process_current_session and
        process_file methods.

        A dictionary on the following form::

            {
                "Settings Name": {
                    "type": "settings_type",
                    "default": "default_value",
                    "description": "One line description of the setting"
            }

        The type string should be one of the data types that toolkit accepts as
        part of its environment configuration.
        """

        # grab any base class settings
        collector_settings = super(NukeSessionCollector, self).settings or {}

        # settings specific to this collector
        nuke_session_settings = {
            "Work file Template": {
                "type": "template",
                "default": None,
                "description": "Template path for artist work files. Should "
                               "correspond to a template defined in "
                               "templates.yml. If configured, is made available"
                               "to publish plugins via the collected item's "
                               "properties. ",
            },
        }

        # update the base settings with these settings
        collector_settings.update(nuke_session_settings)

        return collector_settings

    def process_current_session(self, settings, parent_item):
        """
        Analyzes the current session open in Nuke/NukeStudio and parents a
        subtree of items under the parent_item passed in.

        :param dict settings: Configured settings for this collector
        :param parent_item: Root item instance
        """

        publisher = self.parent
        engine = publisher.engine

        if ((hasattr(engine, "studio_enabled") and engine.studio_enabled) or
            (hasattr(engine, "hiero_enabled") and engine.hiero_enabled)):

            # running nuke studio or hiero
            self.collect_current_nukestudio_session(settings, parent_item)

            # since we're in NS, any additional collected outputs will be
            # parented under the root item
            project_item = parent_item
        else:
            # running nuke. ensure additional collected outputs are parented
            # under the session
            project_item = self.collect_current_nuke_session(settings,
                parent_item)

        # run node collection if not in hiero
        if hasattr(engine, "hiero_enabled") and not engine.hiero_enabled:
            self.collect_node_outputs(project_item)

        # TODO: collect tk nuke write nodes

    def collect_current_nuke_session(self, settings, parent_item):
        """
        Analyzes the current session open in Nuke and parents a subtree of items
        under the parent_item passed in.

        :param dict settings: Configured settings for this collector
        :param parent_item: Root item instance
        """

        publisher = self.parent

        # get the current path
        path = _session_path()

        # determine the display name for the item
        if path:
            file_info = publisher.util.get_file_path_components(path)
            display_name = file_info["filename"]
        else:
            display_name = "Current Nuke Session"

        # create the session item for the publish hierarchy
        project_item = parent_item.create_item(
            "nuke.session",
            "Nuke Script",
            display_name
        )

        # get the icon path to display for this item
        icon_path = os.path.join(
            self.disk_location,
            os.pardir,
            "icons",
            "nuke.png"
        )
        project_item.set_icon_from_path(icon_path)

        # if a work file template is defined, add it to the item properties so
        # that it can be used by attached publish plugins
        work_template_setting = settings.get("Work file Template")
        if work_template_setting:
            work_template = publisher.engine.get_template_by_name(
                work_template_setting.value)

            # store the template on the item for use by publish plugins. we
            # can't evaluate the fields here because there's no guarantee the
            # current session path won't change once the item has been created.
            # the attached publish plugins will need to resolve the fields at
            # execution time.
            project_item.properties["work_file_template"] = work_template
            self.logger.debug(
                "Work file template defined for Nuke collection.")

        self.logger.info("Collected current Nuke script")
        return project_item

    def collect_current_nukestudio_session(self, settings, parent_item):
        """
        Analyzes the current session open in NukeStudio and parents a subtree of
        items under the parent_item passed in.

        :param dict settings: Configured settings for this collector
        :param parent_item: Root item instance
        """

        # import here since the hooks are imported into nuke and nukestudio.
        # hiero module is only available in later versions of nuke
        import hiero.core

        publisher = self.parent

        # go ahead and build the path to the icon for use by any projects
        icon_path = os.path.join(
            self.disk_location,
            os.pardir,
            "icons",
            "nukestudio.png"
        )

        active_project = hiero.ui.activeSequence().project()

        # attempt to retrive a configured work file template. we can attach
        # it to the collected project items
        work_template_setting = settings.get("Work file Template")
        work_template = None
        if work_template_setting:
            work_template = publisher.engine.get_template_by_name(
                work_template_setting.value)

        for project in hiero.core.projects():

            # create the session item for the publish hierarchy
            project_item = parent_item.create_item(
                "nukestudio.project",
                "NukeStudio Project",
                project.name()
            )
            project_item.set_icon_from_path(icon_path)

            # add the project object to the properties so that the publish
            # plugins know which open project to associate with this item
            project_item.properties["project"] = project

            self.logger.info(
                "Collected Nuke Studio project: %s" % (project.name(),))

            # enable the active project and expand it. other projects are
            # collapsed and disabled.
            if active_project and active_project.guid() == project.guid():
                project_item.expanded = True
                project_item.checked = True
            elif active_project:
                # there is an active project, but this isn't it. collapse and
                # disable this item
                project_item.expanded = False
                project_item.checked = False

            # store the template on the item for use by publish plugins. we
            # can't evaluate the fields here because there's no guarantee the
            # current session path won't change once the item has been created.
            # the attached publish plugins will need to resolve the fields at
            # execution time.
            if work_template:
                project_item.properties["work_file_template"] = work_template
                self.logger.debug(
                    "Work file template defined for NukeStudio collection.")

    def collect_node_outputs(self, parent_item):
        """
        Scan known output node types in the session and see if they reference
        files that have been written to disk.

        :param parent_item: The parent item for any write geo nodes collected
        """

        # iterate over all the known output types
        for node_type in _NUKE_OUTPUTS:

            # get all the instances of the node type
            all_nodes_of_type = [n for n in nuke.allNodes()
                if n.Class() == node_type]

            # iterate over each instance
            for node in all_nodes_of_type:

                param_name = _NUKE_OUTPUTS[node_type]

                # evaluate the output path parameter which may include frame
                # expressions/format
                file_path = node[param_name].evaluate()

                if not file_path or not os.path.exists(file_path):
                    # no file or file does not exist, nothing to do
                    continue

                self.logger.info(
                    "Processing %s node: %s" % (node_type, node.name()))

                # file exists, let the basic collector handle it
                item = super(NukeSessionCollector, self)._collect_file(
                    parent_item,
                    file_path,
                    frame_sequence=True
                )

                # the item has been created. update the display name to include
                # the nuke node to make it clear to the user how it was
                # collected within the current session.
                item.name = "%s (%s)" % (item.name, node.name())


def _session_path():
    """
    Return the path to the current session
    :return:
    """
    root_name = nuke.root().name()
    return None if root_name == "Root" else root_name
