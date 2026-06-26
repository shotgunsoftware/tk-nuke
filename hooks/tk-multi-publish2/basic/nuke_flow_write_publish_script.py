# Copyright (c) 2017 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import sgtk

from tank_vendor.flow_integration_sdk.objects import FlowAsset

HookBaseClass = sgtk.get_hook_baseclass()


class NukeFlowWritePublishPlugin(HookBaseClass):

    @property
    def item_filters(self):
        """
        List of item types that this plugin is interested in.

        Only items matching entries in this list will be presented to the
        accept() method. Strings can contain glob patters such as *, for example
        ["maya.*", "file.maya"]
        """

        # TODO: adjust to handle movie files
        return ["file.image.sequence"]  # matches what collect_flow_writenodes() creates

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

        # Only handle renders from FlowWrite node source
        if not item.properties.get("is_nuke_flow_write"):
            return {"accepted": False}
        return {"accepted": True, "checked": True}

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

        # If this is a first publish, we must have a parent id
        # Otherwise, we must have an existin asset id to publish to
        if not item.properties.get("flow_parent_id") and not item.properties.get(
            "flow_asset_id"
        ):
            error_msg = "Missing critical information for publish. "
            error_msg += "FlowWrite node must have source_asset_id and/or asset_id set."
            self.logger.error(error_msg)
            return False

        # Ensure that we have access to the original FlowWrite node
        # to do required post-publish manipulation
        if not item.properties.get("flow_write_node"):
            error_msg = "No FlowWrite node associated with item. "
            error_msg += "This is required to complete post-publish processes."
            self.logger.error(error_msg)
            return False

        return super().validate(settings, item)

    def publish(self, settings, item):
        """
        Executes the publish logic for the given item and settings.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """
        # If there is no asset id associated with item,
        # assume this is a new asset
        first_flow_write_publish = item.properties.get("flow_asset_id") == ""

        # Do base publish
        super().publish(settings, item)

        # Post first publish of a FlowWriteNode, we must store the
        # newly established asset id back on the node and save the
        # file to preserve it
        if first_flow_write_publish:
            node = item.properties.get("flow_write_node")
            pub_info = item.properties.get("am_publish_info")
            asset_id = FlowAsset.get_asset_id(pub_info.revision_id)
            self.logger.info(
                f'Setting asset id on FlowWrite node "{node.name()}": {asset_id}'
            )
            node["asset_id"].setValue(asset_id)
            node["asset_name"].setValue(pub_info.asset_name)
            host = sgtk.platform.current_engine().flow_host
            self.logger.info("Saving nuke script...")
            host.save_file(host.current_file())
