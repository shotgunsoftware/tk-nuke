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
import pprint
import sgtk
from sgtk.platform.qt import QtGui
from sgtk.util.filesystem import copy_file

HookBaseClass = sgtk.get_hook_baseclass()


class NukeStudioProjectPublishPlugin(HookBaseClass):
    """
    Plugin for publishing a Nuke Studio project.
    """

    @property
    def icon(self):
        """
        Path to an png icon on disk
        """

        # look for icon one level up from this hook's folder in "icons" folder
        return os.path.join(
            self.disk_location,
            os.pardir,
            "icons",
            "publish.png"
        )

    @property
    def name(self):
        """
        One line display name describing the plugin
        """
        return "Publish to Shotgun"

    @property
    def description(self):
        """
        Verbose, multi-line description of what the plugin does. This can
        contain simple html for formatting.
        """

        loader_url = "https://support.shotgunsoftware.com/hc/en-us/articles/219033078"

        return """
        Publishes the file to Shotgun. A <b>Publish</b> entry will be
        created in Shotgun which will include a reference to the file's current
        path on disk. If a publish file template is configured, a copy of the
        current session will be copied to the publish file template path which
        will be the file that is published. Other users will be able to access
        the published file via the <b><a href='%s'>Loader</a></b> so long as
        they have access to the file's location on disk.

        If the session has not been saved, validation will fail and a button
        will be provided in the logging output to save the file.

        <h3>File versioning</h3>
        If the filename contains a version number, the process will bump the
        file to the next version after publishing.

        The <code>version</code> field of the resulting <b>Publish</b> in
        Shotgun will also reflect the version number identified in the filename.
        The basic worklfow recognizes the following version formats by default:

        <ul>
        <li><code>filename.v###.ext</code></li>
        <li><code>filename_v###.ext</code></li>
        <li><code>filename-v###.ext</code></li>
        </ul>

        After publishing, if a version number is detected in the work file, the
        work file will automatically be saved to the next incremental version
        number. For example, <code>filename.v001.ext</code> will be published
        and copied to <code>filename.v002.ext</code>

        If the next incremental version of the file already exists on disk, the
        validation step will produce a warning, and a button will be provided in
        the logging output which will allow saving the session to the next
        available version number prior to publishing.

        <br><br><i>NOTE: any amount of version number padding is supported. for
        non-template based workflows.</i>

        <h3>Overwriting an existing publish</h3>
        In non-template workflows, a file can be published multiple times,
        however only the most recent publish will be available to other users.
        Warnings will be provided during validation if there are previous
        publishes.
        """ % (loader_url,)
        # TODO: add link to workflow docs

    @property
    def settings(self):
        """
        Dictionary defining the settings that this plugin expects to receive
        through the settings parameter in the accept, validate, publish and
        finalize methods.

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
        return {
            "Publish Type": {
                "type": "shotgun_publish_type",
                "default": "NukeStudio Project",
                "description": "SG publish type to associate publishes with."
            },
            "Publish file Template": {
                "type": "template",
                "default": None,
                "description": "Template path for published work files. Should"
                               "correspond to a template defined in "
                               "templates.yml.",
            }
        }

    @property
    def item_filters(self):
        """
        List of item types that this plugin is interested in.

        Only items matching entries in this list will be presented to the
        accept() method. Strings can contain glob patters such as *, for example
        ["maya.*", "file.maya"]
        """
        return ["nukestudio.project"]

    def accept(self, settings, item):
        """
        Method called by the publisher to determine if an item is of any
        interest to this plugin. Only items matching the filters defined via the
        item_filters property will be presented to this method.

        A publish task will be generated for each item accepted here. Returns a
        dictionary with the following booleans:

            - accepted: Indicates if the plugin is interested in this value at
                all. Required.
            - enabled: If True, the plugin will be enabled in the UI, otherwise
                it will be disabled. Optional, True by default.
            - visible: If True, the plugin will be visible in the UI, otherwise
                it will be hidden. Optional, True by default.
            - checked: If True, the plugin will be checked in the UI, otherwise
                it will be unchecked. Optional, True by default.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process

        :returns: dictionary with boolean keys accepted, required and enabled
        """

        self.logger.debug("HERE HERE HERE")

        project = item.properties.get("project")
        if not project:
            self.logger.warn("Could not determine the project.")
            return {"accepted": False}

        path = project.path()

        if not path:
            # the session has not been saved before (no path determined).
            # provide a save button. the session will need to be saved before
            # validation will succeed.
            self.logger.warn(
                "The Nuke Studio project '%s' has not been saved." %
                (project.name()),
                extra=_get_save_as_action(project)
            )

        self.logger.info(
            "Nuke Studio '%s' plugin accepted project: %s." %
            (self.name, project.name())
        )
        return {
            "accepted": True,
            "checked": True
        }

    def validate(self, settings, item):
        """
        Validates the given item to check that it is ok to publish. Returns a
        boolean to indicate validity.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        :returns: True if item is valid, False otherwise.
        """

        publisher = self.parent
        project = item.properties.get("project")
        path = project.path()

        if not path:
            # the session still requires saving. provide a save button.
            # validation fails.
            self.logger.error(
                "The Nuke Studio project '%s' has not been saved." %
                (project.name(),),
                extra=_get_save_as_action(project)
            )
            return False

        # get the path in a normalized state. no trailing separator,
        # separators are appropriate for current os, no double separators,
        # etc.
        sgtk.util.ShotgunPath.normalize(path)

        # get the path in a normalized state. no trailing separator,
        # separators are appropriate for current os, no double separators,
        # etc.
        sgtk.util.ShotgunPath.normalize(path)

        # if the session item has a known work file template, see if the path
        # matches. if not, warn the user and provide a way to save the file to
        # a different path
        work_file_template = item.properties.get("work_file_template")
        if work_file_template:
            if not work_file_template.validate(path):
                self.logger.warning(
                    "The current session does not match the configured work "
                    "file template.",
                    extra={
                        "action_button": {
                            "label": "Save File",
                            "tooltip": "Save the current Houdini session to a "
                                       "different file name",
                            # will launch wf2 if configured
                            "callback": _get_save_as_action(project)
                        }
                    }
                )
        else:
            self.logger.debug("No work file template configured.")

        # determine the publish path, version, type, and name
        publish_info = self._get_publish_info(path, settings, item)

        publish_name = publish_info["name"]

        # see if there are any other publishes of this path with a status.
        # Note the name, context, and path *must* match the values supplied to
        # register_publish in the publish phase in order for this to return an
        # accurate list of previous publishes of this file.
        publishes = publisher.util.get_conflicting_publishes(
            item.context,
            path,
            publish_name,
            filters=["sg_status_list", "is_not", None]
        )

        if publishes:
            conflict_info = (
                "If you continue, these conflicting publishes will no longer "
                "be available to other users via the loader:<br>"
                "<pre>%s</pre>" % (pprint.pformat(publishes),)
            )
            self.logger.warn(
                "Found %s conflicting publishes in Shotgun" %
                (len(publishes),),
                extra={
                    "action_show_more_info": {
                        "label": "Show Conflicts",
                        "tooltip": "Show the conflicting publishes in Shotgun",
                        "text": conflict_info
                    }
                }
            )

        # check to see if the next version of the work file already exists on
        # disk. if so, warn the user and provide the ability to jump to save
        # to that version now
        (next_version_path, version) = self._get_next_version_info(path, item)
        if next_version_path and os.path.exists(next_version_path):

            # determine the next available version_number. just keep asking for
            # the next one until we get one that doesn't exist.
            while os.path.exists(next_version_path):
                (next_version_path, version) = self._get_next_version_info(
                    next_version_path, item)

            self.logger.error(
                "The next version of this file already exists on disk.",
                extra={
                    "action_button": {
                        "label": "Save to v%s" % (version,),
                        "tooltip": "Save to the next available version number, "
                                   "v%s" % (version,),
                        "callback": lambda: project.saveAs(next_version_path)
                    }
                }
            )
            return False

        self.logger.info("A Publish will be created in Shotgun and linked to:")
        self.logger.info("  %s" % (path,))

        return True

    def publish(self, settings, item):
        """
        Executes the publish logic for the given item and settings.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """

        publisher = self.parent
        project = item.properties.get("project")
        path = project.path()

        # get the path in a normalized state. no trailing separator, separators
        # are appropriate for current os, no double separators, etc.
        path = sgtk.util.ShotgunPath.normalize(path)

        # ensure the session is saved
        project.saveAs(path)

        # get all the publish info extracted during validation
        publish_info = self._get_publish_info(path, settings, item)
        publish_path = publish_info["path"]

        # if the path doesn't match the publish path, copy the file to the
        # publish path
        if path != publish_path and not os.path.exists(publish_path):
            publish_folder = os.path.dirname(publish_path)
            publisher.ensure_folder_exists(publish_folder)
            copy_file(path, publish_path)
            self.logger.debug(
                "Copied work file (%s) to publish path (%s)" %
                (path, publish_path)
            )

        # arguments for publish registration
        self.logger.info("Registering publish...")
        publish_data = {
            "tk": publisher.sgtk,
            "context": item.context,
            "comment": item.description,
            "path": publish_path,
            "name": publish_info["name"],
            "version_number": publish_info["version"],
            "thumbnail_path": item.get_thumbnail_as_path(),
            "published_file_type": settings["Publish Type"].value,
            "dependency_paths": []
        }

        # log the publish data for debugging
        self.logger.debug(
            "Populated Publish data...",
            extra={
                "action_show_more_info": {
                    "label": "Publish Data",
                    "tooltip": "Show the complete Publish data dictionary",
                    "text": "<pre>%s</pre>" % (pprint.pformat(publish_data),)
                }
            }
        )

        # store for use in finalize now that the publish is complete
        item.properties["work_file_path"] = path
        item.properties["publish_info"] = publish_info

        # create the publish and stash it in the item properties for other
        # plugins to use.
        item.properties["sg_publish_data"] = sgtk.util.register_publish(
            **publish_data)

        # inject the publish path such that children can refer to it when
        # updating dependency information
        item.properties["sg_publish_path"] = path

        self.logger.info("Publish registered!")

    def finalize(self, settings, item):
        """
        Execute the finalization pass. This pass executes once all the publish
        tasks have completed, and can for example be used to version up files.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """

        publisher = self.parent
        project = item.properties.get("project")

        # get the data for the publish that was just created in SG
        publish_data = item.properties["sg_publish_data"]

        # ensure conflicting publishes have their status cleared
        publisher.util.clear_status_for_conflicting_publishes(
            item.context, publish_data)

        self.logger.info(
            "Cleared the status of all previous, conflicting publishes")

        publish_path = item.properties["publish_info"]["path"]

        path = item.properties["work_file_path"]

        self.logger.info(
            "Publish created for file: %s" % (publish_path,),
            extra={
                "action_show_in_shotgun": {
                    "label": "Show Publish",
                    "tooltip": "Open the Publish in Shotgun.",
                    "entity": publish_data
                }
            }
        )

        # insert the path into the properties
        item.properties["next_version_path"] = self._bump_file_version(
            project, path, item)

    def _bump_file_version(self, project, path, item):
        """
        Save the supplied path to the next version on disk.
        """

        (next_version_path, version) = self._get_next_version_info(path, item)

        if version is None:
            self.logger.debug(
                "No version number detected in the publish path. "
                "Skipping the bump file version step."
            )
            return None

        self.logger.info("Incrementing session file version number...")

        # nothing to do if the next version path can't be determined or if it
        # already exists.
        if not next_version_path:
            self.logger.warning("Could not determine the next version path.")
            return None
        elif os.path.exists(next_version_path):
            self.logger.warning(
                "The next version of the path already exists",
                extra={
                    "action_show_folder": {
                        "path": next_version_path
                    }
                }
            )
            return None

        # save the session to the new path
        project.saveAs(next_version_path)
        self.logger.info("Session saved as: %s" % (next_version_path,))

        return next_version_path

    def _get_next_version_info(self, path, item):
        """
        Return the next version of the supplied path.

        If templates are configured, use template logic. Otherwise, fall back to
        the zero configuration, path_info hook logic.

        :param str path: A path with a version number.
        :param item: The session item

        :return: A tuple of the form::

            # the first item is the supplied path with the version bumped by 1
            # the second item is the new version number
            (next_version_path, version)
        """

        if not path:
            self.logger.debug("Path is None. Can not determine version info.")
            return None, None

        publisher = self.parent

        # if the session item has a known work file template, see if the path
        # matches. if not, warn the user and provide a way to save the file to
        # a different path
        work_template = item.properties.get("work_file_template")
        work_fields = None

        if work_template:
            if work_template.validate(path):
                self.logger.debug(
                    "Work file template configured and matches session file.")

                work_fields = work_template.get_fields(path)

        # if we have template and fields, use them to determine the version info
        if work_template and work_fields and "version" in work_fields:
            self.logger.debug(
                "Using work file template to determine next version.")

            # template matched. bump version number and re-apply to the template
            work_fields["version"] += 1
            next_version_path = work_template.apply_fields(work_fields)
            version = work_fields["version"]

        # fall back to the "zero config" logic
        else:
            self.logger.debug("Using path info hook to determine next version.")
            next_version_path = publisher.util.get_next_version_path(path)
            cur_version = publisher.util.get_version_number(path)
            if cur_version:
                version = cur_version + 1
            else:
                version = None

        return next_version_path, version

    def _get_publish_info(self, path, settings, item):
        """
        This method encompasses the logic for extracting the publish path,
        version, type, and name given the path to the current session.

        If templates are configured they will be used to identify the publish
        path. If templates are not configured, the publish-in-place logic will
        be used.

        :param str path: The path to the current session
        :param dict settings: Configured publish settings

        :return: A dictionary of the form::

            {
                "path": "/path/to/file/to/publish/filename.v0001.ma",
                "name": "filename.ma",
                "version": 1,
                "type": "Maya Scene"
            }
        """

        publisher = self.parent

        # publish type comes from the plugin settings
        publish_type = settings["Publish Type"].value

        # ---- Check to see if templates are in play

        work_template = item.properties.get("work_file_template")
        work_fields = None

        if work_template:
            if work_template.validate(path):
                self.logger.debug(
                    "Work file template configured and matches session file.")

                work_fields = work_template.get_fields(path)

        # the configured publish file template
        publish_template = None
        publish_template_setting = settings.get("Publish file Template")

        if publish_template_setting:
            # template setting defined, get the template itself
            publish_template = publisher.engine.get_template_by_name(
                publish_template_setting.value)

        if work_fields and publish_template:

            # templates in play. use them to extract the info we need.
            self.logger.debug(
                "Using publish template to determine publish info.")

            # scene path matches the work file template. execute the
            # "classic" toolkit behavior of constructing the output publish
            # path and copying the work file to that location
            work_fields["TankType"] = publish_type

            # construct the publish path
            publish_path = publish_template.apply_fields(work_fields)

            self.logger.debug("Publish path: %s" % (publish_path,))

            # if version number is one of the fields, use it to populate the
            # publish information, else fall back to the default version,
            # extracted from the work file above
            version_number = work_fields.get("version", 1)

            self.logger.debug("Version number: %s" % (version_number,))

        else:
            self.logger.debug("Using path info hook to determine publish info.")
            publish_path = path
            version_number = publisher.util.get_version_number(path) or 1

        # get the publish name for the publish file. this will ensure we get a
        # consistent name across version publishes of this file and regardless
        # of whether we're using templates or zero config path resolution.
        publish_name = publisher.util.get_publish_name(publish_path)

        return {
            "path": publish_path,
            "name": publish_name,
            "version": version_number,
            "type": publish_type,
        }


def _get_save_as_action(project):
    """
    Simple helper for returning a log action dict for saving the session
    """
    return {
        "action_button": {
            "label": "Save As...",
            "tooltip": "Save the current session",
            "callback": lambda: _project_save_as(project)
        }
    }


def _project_save_as(project):
    """
    A save as wrapper for the current session.

    :param path: Optional path to save the current session as.
    """
    # TODO: consider moving to engine

    # import here since the hooks are imported into nuke and nukestudio.
    # hiero module is only available in later versions of nuke
    import hiero

    # nuke studio/hiero don't appear to have a "save as" dialog accessible via
    # python. so open our own Qt file dialog.
    file_dialog = QtGui.QFileDialog(
        parent=hiero.ui.mainWindow(),
        caption="Save As",
        directory=project.path(),
        filter="Nuke Studio Files (*.hrox)"
    )
    file_dialog.setLabelText(QtGui.QFileDialog.Accept, "Save")
    file_dialog.setLabelText(QtGui.QFileDialog.Reject, "Cancel")
    file_dialog.setOption(QtGui.QFileDialog.DontResolveSymlinks)
    file_dialog.setOption(QtGui.QFileDialog.DontUseNativeDialog)
    if not file_dialog.exec_():
        return
    path = file_dialog.selectedFiles()[0]
    project.saveAs(path)

