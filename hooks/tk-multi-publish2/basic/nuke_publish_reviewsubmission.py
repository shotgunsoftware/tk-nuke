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


class NukeReviewSubmissionPublishPlugin(HookBaseClass):
    """
    Plugin for publishing an open nuke session.

    This hook relies on functionality found in the base file publisher hook in
    the publish2 app and should inherit from it in the configuration. The hook
    setting for this plugin should look something like this::

        hook: "{self}/publish_file.py:{engine}/tk-multi-publish2/basic/nuke_publish_script.py"

    """

    # NOTE: The plugin icon and name are defined by the base file plugin.

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
        path on disk. If a publish template is configured, a copy of the
        current session will be copied to the publish template path which
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

        # inherit the settings from the base publish plugin
        base_settings = super(NukeReviewSubmissionPublishPlugin, self).settings or {}

        # settings specific to this class
        nuke_publish_settings = {
            "Publish Template": {
                "type": "template",
                "default": None,
                "description": "Template path for published work files. Should"
                               "correspond to a template defined in "
                               "templates.yml.",
            }
        }

        # update the base settings
        base_settings.update(nuke_publish_settings)

        return base_settings

    @property
    def item_filters(self):
        """
        List of item types that this plugin is interested in.

        Only items matching entries in this list will be presented to the
        accept() method. Strings can contain glob patters such as *, for example
        ["maya.*", "file.maya"]
        """
        return ["nuke.reviewsubmission"]

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

        accepted = True
        # if a publish template is configured, disable context change. This
        # is a temporary measure until the publisher handles context switching
        # natively.
        if settings.get("Publish Template").value:
            item.context_change_allowed = False
        review_submission_app = self.parent.engine.apps.get("tk-multi-reviewsubmission")
        if review_submission_app is None:
            accepted = False
            self.logger.warning(
                "Review submission app is not available. skipping item: %s" %
                (item.properties["publish_name"],)
            )
        write_node_app = self.parent.engine.apps.get("tk-nuke-writenode")
        if write_node_app is None:
            accepted = False
            self.logger.warning(
                "Write Node app is not available. skipping item: %s" %
                (item.properties["publish_name"],)
            )

        if accepted:
            self.logger.info(
                "Nuke review submission item '%s' is accepted by the plugin." %
                (item.properties["publish_name"],)
            )
        return {
            "accepted": accepted,
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

        review_submission_app = self.parent.engine.apps.get("tk-multi-reviewsubmission")
        if review_submission_app is None:
            error_msg = "Item cannot be validated. Review Submission App is not available."
            self.logger.error(error_msg)
            raise Exception(error_msg)
        write_node_app = self.parent.engine.apps.get("tk-nuke-writenode")
        if write_node_app is None:
            error_msg = "Item cannot be validated. Write Node App is not available."
            self.logger.error(error_msg)
            raise Exception(error_msg)

        # the render task will always render full-res frames when publishing. If we're
        # in proxy mode in Nuke, that task will fail since there will be no full-res 
        # frames rendered. The exceptions are if there is no proxy_render_template set 
        # in the tk-nuke-writenode app, then the write node app falls back on the
        # full-res template. Or if they rendered in full res and then switched to 
        # proxy mode later. In this case, this is likely user error, so we catch it.
        root_node = nuke.root()
        proxy_mode_on = root_node['proxy'].value()
        if proxy_mode_on:
            error_msg = "You cannot publish to Screening Room while Nuke is in proxy " +\
                        "mode. Please toggle proxy mode OFF and try again."
            self.logger.error(error_msg)
            raise Exception(error_msg)

        publisher = self.parent

        # populate the publish template on the item if found
        publish_template_setting = settings.get("Publish Template")
        publish_template = publisher.engine.get_template_by_name(
            publish_template_setting.value)
        if publish_template:
            item.properties["publish_template"] = publish_template

        return True

    def publish(self, settings, item):
        """
        Executes the publish logic for the given item and settings.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """

        review_submission_app = self.parent.engine.apps.get("tk-multi-reviewsubmission")
        if review_submission_app is None:
            error_msg = "Item cannot be validated. Review Submission App is not available."
            self.logger.error(error_msg)
            return
        write_node_app = self.parent.engine.apps.get("tk-nuke-writenode")
        if write_node_app is None:
            error_msg = "Item cannot be validated. Write Node App is not available."
            self.logger.error(error_msg)
            return

        self._send_to_screening_room(item,
                                     item.parent.properties["sg_publish_data"],
                                     self.parent.context.task,
                                     item.description,
                                     item.get_thumbnail_as_path(),
                                     lambda *args, **kwargs: None)

    def finalize(self, settings, item):
        """
        Execute the finalization pass. This pass executes once all the publish
        tasks have completed, and can for example be used to version up files.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """
        pass

    def _send_to_screening_room(self, item, sg_publish, sg_task, comment, thumbnail_path, progress_cb):
        """
        Take a write node's published files and run them through the review_submission app 
        to get a movie and Shotgun Version.

        :param item:            The item to be published
        :param sg_publish:      The Shotgun publish entity dictionary to link the version with
        :param sg_task:         The Shotgun task entity dictionary for the publish
        :param comment:         The publish comment
        :param thumbnail_path:  The path to a thumbnail for the publish
        :param progress_cb:     A callback to use to report any progress
        """
        write_node_app = self.parent.engine.apps.get("tk-nuke-writenode")
        review_submission_app = self.parent.engine.apps.get("tk-multi-reviewsubmission")

        render_path = item.parent.properties.get("path")
        render_template = item.parent.properties.get("work_template")
        publish_template = item.properties.get("publish_template") or item.parent.properties.get("publish_template")                        
        render_path_fields = render_template.get_fields(render_path)

        if hasattr(review_submission_app, "render_and_submit_version"):
            # this is a recent version of the review submission app that contains
            # the new method that also accepts a colorspace argument.
            colorspace = item.parent.properties.get("color_space")
            review_submission_app.render_and_submit_version(
                publish_template,
                render_path_fields,
                int(nuke.root()["first_frame"].value()),
                int(nuke.root()["last_frame"].value()),
                [sg_publish],
                sg_task,
                comment,
                thumbnail_path,
                progress_cb,
                colorspace
            )
        else:
            # This is an older version of the app so fall back to the legacy
            # method - this may mean the colorspace of the rendered movie is
            # inconsistent/wrong!
            review_submission_app.render_and_submit(
                publish_template,
                render_path_fields,
                int(nuke.root()["first_frame"].value()),
                int(nuke.root()["last_frame"].value()),
                [sg_publish],
                sg_task,
                comment,
                thumbnail_path,
                progress_cb
            )
