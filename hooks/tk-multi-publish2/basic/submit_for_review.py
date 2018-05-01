# Copyright (c) 2017 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import nuke
import os
import sgtk

HookBaseClass = sgtk.get_hook_baseclass()


class NukeSubmitForReviewPlugin(HookBaseClass):
    """
    Plugin for submitting a review from Nuke into Shotgun.

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
            "review.png"
        )

    @property
    def name(self):
        """
        One line display name describing the plugin
        """
        return "Submit for Review"

    @property
    def description(self):
        """
        Verbose, multi-line description of what the plugin does. This can
        contain simple html for formatting.
        """

        review_url = "https://support.shotgunsoftware.com/hc/en-us/articles/114094032014-The-review-workflow"

        return """<p>
        Submits a movie file to Shotgun for review. An entry will be
        created in Shotgun which will include a reference to the movie file's current
        path on disk. Other users will be able to access the file via
        the <b><a href='%s'>review app</a></b> on the Shotgun website.</p>
        """ % (review_url)

    @property
    def settings(self):
        """
        Dictionary defining the settings that this plugin expects to recieve
        through the settings parameter in the accept, validate, publish and
        finalize methods.

        A dictionary on the following form::

            {
                "Settings Name": {
                    "type": "settings_type",
                    "default": "default_value",
                    "description": "One line description of the setting"
            }

        The type string should be one of the data types that toolkit accepts
        as part of its environment configuration.
        """
        return {}

    @property
    def item_filters(self):
        """
        List of item types that this plugin is interested in.

        Only items matching entries in this list will be presented to the
        accept() method. Strings can contain glob patters such as *, for example
        ["maya.*", "file.maya"]
        """
        return ["*.sequence"]

    def accept(self, settings, item):
        """
        Method called by the publisher to determine if an item is of any
        interest to this plugin. Only items matching the filters defined via the
        item_filters property will be presented to this method.

        A submit for review task will be generated for each item accepted here. Returns a
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

        :returns: dictionary with boolean keys accepted, required and enabled. 
            This plugin makes use of the tk-multi-reviewsubmission app; if this
            app is not available then the item will not be accepted, this method
            will return a dictionary with the accepted field that has a value of
            False.

            Several properties on the item must also be present for it to be
            accepted. The properties are 'path', 'publish_name', 'color_space',
            'first_frame' and 'last_frame'
        """

        accepted = True
        review_submission_app = self.parent.engine.apps.get("tk-multi-reviewsubmission")
        if review_submission_app is None:
            accepted = False
            self.logger.debug(
                "Review submission app is not available. skipping item: %s" %
                (item.properties["publish_name"],)
            )
        if item.properties.get("color_space") is None:
            accepted = False
            self.logger.debug(
                "'color_space' property is not defined on the item. "
                "Item will be skipped: %s." %
                (item.properties["publish_name"],)
            )
        if item.properties.get("first_frame") is None:
            accepted = False
            self.logger.debug(
                "'first_frame' property is not defined on the item. "
                "Item will be skipped: %s." %
                (item.properties["publish_name"],)
            )
        if item.properties.get("last_frame") is None:
            accepted = False
            self.logger.debug(
                "'last_frame' property is not defined on the item. "
                "Item will be skipped: %s." %
                (item.properties["publish_name"],)
            )
        path = item.properties.get("path")
        if path is None:
            accepted = False
            self.logger.debug(
                "'path' property is not defined on the item. "
                "Item will be skipped: %s." %
                (item.properties["publish_name"],)
            )

        if accepted:
            # log the accepted file and display a button to reveal it in the fs
            self.logger.info(
                "Submit for review plugin accepted: %s" % (path,),
                extra={
                    "action_show_folder": {
                        "path": path
                    }
                }
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
        :returns: True if item is valid and not in proxy mode, False otherwise.
        """

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

        return True

    def publish(self, settings, item):
        """
        Executes the publish logic for the given item and settings.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """

        render_path = item.properties.get("path")

        sg_publish_data = item.properties.get("sg_publish_data")
        if sg_publish_data is None:
            raise Exception("'sg_publish_data' was not found in the item's properties. "
                            "Review Submission for '%s' failed. This property must "
                            "be set by a publish plugin that has run before this one." % render_path)
        sg_task = self.parent.context.task
        comment = item.description
        thumbnail_path = item.get_thumbnail_as_path()
        progress_cb = lambda *args, **kwargs: None
        review_submission_app = self.parent.engine.apps.get("tk-multi-reviewsubmission")

        render_template = item.properties.get("work_template")
        if render_template is None:
            raise Exception("'work_template' property is missing from item's properties. "
                            "Review submission for '%s' failed." % render_path)
        publish_template = item.properties.get("publish_template")
        if publish_template is None:
            raise Exception("'publish_template' property not found on item. "
                            "Review submission for '%' failed." % render_path)
        if not render_template.validate(render_path):
            raise Exception("'%s' did not match the render template. "
                            "Review submission failed." % render_path)

        render_path_fields = render_template.get_fields(render_path)
        first_frame = item.properties.get("first_frame")
        last_frame = item.properties.get("last_frame")
        colorspace = item.properties.get("color_space")
        
        version = review_submission_app.render_and_submit_version(
                publish_template,
                render_path_fields,
                first_frame,
                last_frame,
                [sg_publish_data],
                sg_task,
                comment,
                thumbnail_path,
                progress_cb,
                colorspace
        )
        if version:
            self.logger.info(
                "Version uploaded for file: %s" % (render_path,),
                extra={
                    "action_show_in_shotgun": {
                        "label": "Show Version",
                        "tooltip": "Reveal the version in Shotgun.",
                        "entity": version
                    }
                }
            )
        else:
            raise Exception("Review submission failed. Could not render and "
                            "submit the review associated sequence.")

    def finalize(self, settings, item):
        """
        Execute the finalization pass. This pass executes once all the publish
        tasks have completed.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """
        pass
