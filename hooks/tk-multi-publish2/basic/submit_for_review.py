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


class NukeSubmitForReviewPlugin(HookBaseClass):
    """
    Plugin for submitting a review movie from a Nuke session write node.

    This hook relies on functionality found in the base submit for review hook in
    the publish2 app and should inherit from it in the configuration. The hook
    setting for this plugin should look something like this::

        hook: "{self}/submit_for_review.py:{engine}/tk-multi-publish2/basic/submit_for_review.py"

    """

    def validate(self, settings, item):
        """
        Validates the given item to check that it is ok to submit for review. Returns a
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

        return super(NukeSubmitForReviewPlugin, self).validate(settings, item)

    def finalize(self, settings, item):
        """
        Execute the finalization pass. This pass executes once all the submission
        tasks have completed.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """
        pass
