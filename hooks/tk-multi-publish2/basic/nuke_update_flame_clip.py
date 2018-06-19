# Copyright (c) 2017 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import datetime
import os
import shutil
import uuid
import xml.dom.minidom as minidom
import glob
import re

import sgtk

from sgtk.util import (
    get_published_file_entity_type,
    resolve_publish_path,
    register_publish,
)

CLIP_PUBLISH_TYPE = "Flame Batch OpenClip"

HookBaseClass = sgtk.get_hook_baseclass()


class UpdateFlameClipPlugin(HookBaseClass):
    """
    Updates the flame clip associated with the current Shot.
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
            "flame.png"
        )

    @property
    def name(self):
        """
        One line display name describing the plugin
        """
        return "Update Flame Clip"

    @property
    def description(self):
        """
        Verbose, multi-line description of what the plugin does. This can
        contain simple html for formatting.
        """

        return """
        This plugin updates the Flame clip for the output Shot context. This is
        part of the Flame Export workflow.
        """

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

        # settings specific to this class
        return {
            "Flame Clip Template": {
                "type": "template",
                "default": None,
                "description": "Template path for flame shot clip path."
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
        return ["*.sequence"]

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

        publisher = self.parent

        # In the situation where the writenode app is being used, we
        # only want to associate the clip file lookup/update with
        # the output from the managed write nodes.
        #
        # In the case where there's no writenode associated with the
        # environment we're a bit less restrictive. In that case we're
        # likely in a zero-config situation, which means we can't
        # expect everything written from the session to be path managed.
        # As a result, we accept all image sequences written from the
        # Nuke script.
        sg_writenode_app = publisher.engine.apps.get("tk-nuke-writenode")
        if sg_writenode_app:
            self.logger.debug("Nuke write node app is installed")
            item.properties["sg_writenode_app"] = sg_writenode_app

            # Ensure this item is associated with a nuke write node.
            if item.properties.get("sg_writenode"):
                self.logger.debug("Nuke write node instance found on item.")
            else:
                self.logger.debug(
                    "Unable to identify a nuke writenode instance for this item. "
                    "Plugin %s no accepting item: %s" % (self, item)
                )
                return {"accepted": False}

        # Check to see if we have a template to use. In that case,
        # we'll be trying to find a clip file at that location. If we
        # don't have a template configured, or the clip file doesn't
        # exist at that location on disk, we'll look for a published
        # clip.
        flame_clip_template_setting = settings.get("Flame Clip Template")
        flame_clip_template = publisher.engine.get_template_by_name(
            flame_clip_template_setting.value
        )

        if flame_clip_template:
            # get the clip template and try to build the path from the item's
            # context. if the path can be built, we're good to go.
            self.logger.debug("Flame clip template configured for this plugin.")
            flame_clip_fields = item.context.as_template_fields(flame_clip_template)
            flame_clip_path = flame_clip_template.apply_fields(flame_clip_fields)

            # Just because we have a template and can build the path where
            # the clip would exist doesn't mean it's actually there.
            if os.path.exists(flame_clip_path):
                item.properties["flame_clip_path"] = flame_clip_path
        elif item.context.entity:
            self.logger.debug("Attempting to find OpenClip publish in %s..." % item.context)

            # TODO: We have a problem. The publish2 plugin acceptance routines
            # are not re-run when the item's link changes. This means if the
            # context hasn't been set to a shot using the panel app before
            # publish2 is launched, we end up running this in the project
            # context, which is never going to work for us here. Because we
            # then aren't re-run if the user change's the item's link to be
            # a Shot, we don't look for a clip file when we should have.
            #
            # As a fallback to the traditional approach of looking up the clip
            # path using templates, we now look for a matching PublishedFile
            # entity. This situation arises when dealing with publishes coming
            # from Flame 2019+, which makes use of the publish2 app instead of
            # the old flame export app.
            #
            # We're going to do a middle-ground approach when it comes to multiple
            # clips published to the same shot. If there are multiple clips, we're
            # going to iterate over each one, newest to oldest, until we find
            # one that exists locally. Once we find that, we use it.
            #
            # In most cases this will not do anything differently than the template
            # driven solution, because we'll have a single OpenClip published for
            # the shot, but there might be cases where this heads off a problem.
            publish_entity_type = get_published_file_entity_type(publisher.sgtk)

            self.logger.debug("Clip publish types to search for: %s" % CLIP_PUBLISH_TYPE)

            clip_publishes = publisher.shotgun.find(
                publish_entity_type,
                [
                    ["entity", "is", item.context.entity],
                    ["published_file_type.PublishedFileType.code", "is", CLIP_PUBLISH_TYPE],
                ],
                fields=(
                    "path",
                    "version_number",
                    "name",
                    "published_file_type",
                    "description",
                ),
                order=[dict(field_name="id", direction="desc")],
            )

            if clip_publishes:
                self.logger.debug("Found published clips: %s" % clip_publishes)

            for clip_publish in clip_publishes:
                self.logger.debug("Checking existence of OpenClip: %s" % clip_publish)

                try:
                    flame_clip_path = resolve_publish_path(publisher.sgtk, clip_publish)
                except Exception:
                    self.logger.debug("Unable to resolve path: %s" % clip_publish)
                    continue

                if os.path.exists(flame_clip_path):
                    # If we already found a newer clip that we're going to use, we
                    # log the fact that the others will NOT be used for the sake of
                    # transparency and debuggability.
                    if item.properties.get("flame_clip_path"):
                        self.logger.warning(
                            "The following clip exists, but will not be updated since a "
                            "newer publish exists: %s" % flame_clip_path
                        )
                        continue
                    else:
                        self.logger.info("Clip publish found: %s" % flame_clip_path)

                    # Keep track of the PublishedFile entity. We'll need it
                    # later when the clip is updated, at which time we'll
                    # be versioning up the PublishedFile.
                    item.properties["flame_clip_publish"] = clip_publish
                    item.properties["flame_clip_path"] = flame_clip_path
                else:
                    self.logger.debug(
                        "Published clip file isn't accessible: %s" % flame_clip_path
                    )
        else:
            self.logger.debug(
                "Unable to look up a clip file to update. No template exists, "
                "and the item's context is not associated with an entity."
            )

        if not item.properties.get("flame_clip_path"):
            self.logger.debug(
                "No flame clip was found to update. "
                "Plugin %s not accepting item: %s" % (self, item)
            )

        return {"accepted": (item.properties.get("flame_clip_path") is not None)}

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
        return True

    def publish(self, settings, item):
        """
        Executes the publish logic for the given item and settings.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """
        try:
            # update shot clip xml file with this publish
            self._update_flame_clip(item)
        except Exception as exc:
            raise Exception("Unable to update Flame clip xml: %s" % exc)

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

    def _update_flame_clip(self, item):
        """
        Update the Flame open clip file for this shot with the published render.
        When a shot has been exported from flame, a clip file is available for
        each shot. We load that up, parse the xml and add a new entry to it.

        For docs on the clip format, see:

        http://knowledge.autodesk.com/support/flame-products/troubleshooting/caas/sfdcarticles/sfdcarticles/Creating-clip-Open-Clip-files-from-multi-EXR-assets.html
        http://docs.autodesk.com/flamepremium2015/index.html?url=files/GUID-1A051CEB-429B-413C-B6CA-256F4BB5D254.htm,topicNumber=d30e45343

        When the clip file is updated, a new <version> tag and a new <feed> tag are inserted::

            <feed type="feed" vuid="v002" uid="DA62F3A2-BA3B-4939-8089-EC7FC603AC74">
                <spans type="spans" version="4">
                    <span type="span" version="4">
                        <path encoding="pattern">/nuke/publish/path/mi001_scene_output_v001.[0100-0150].dpx</path>
                    </span>
                </spans>
            </feed>
            <version type="version" uid="v002">
                <name>Comp, scene.nk, v003</name>
                <creationDate>2014/12/09 22:30:04</creationDate>
                <userData type="dict">
                </userData>
            </version>
            An example clip XML file would look something like this:
            <?xml version="1.0" encoding="UTF-8"?>
            <clip type="clip" version="4">
                <handler type="handler">
                    ...
                </handler>
                <name type="string">mi001</name>
                <sourceName type="string">F004_C003_0228F8</sourceName>
                <userData type="dict">
                    ...
                </userData>
                <tracks type="tracks">
                    <track type="track" uid="video">
                        <trackType>video</trackType>
                        <dropMode type="string">NDF</dropMode>
                        <duration type="time" label="00:00:07+02">
                            <rate type="rate">
                                <numerator>24000</numerator>
                                <denominator>1001</denominator>
                            </rate>
                            <nbTicks>170</nbTicks>
                            <dropMode>NDF</dropMode>
                        </duration>
                        <name type="string">mi001</name>
                        <userData type="dict">
                            <GATEWAY_NODE_ID type="binary">/mnt/projects/arizona_adventure/sequences/Mirage/mi001/editorial/flame/mi001.clip@TRACK(5)video</GATEWAY_NODE_ID>
                            <GATEWAY_SERVER_ID type="binary">10.0.1.8:Gateway</GATEWAY_SERVER_ID>
                            <GATEWAY_SERVER_NAME type="string">xxx</GATEWAY_SERVER_NAME>
                        </userData>
                        <feeds currentVersion="v002">
                            <feed type="feed" vuid="v000" uid="5E21801C-41C2-4B47-90B6-C1E25235F032">
                                <storageFormat type="format">
                                    <type>video</type>
                                    <channelsDepth type="uint">10</channelsDepth>
                                    <channelsEncoding type="string">Integer</channelsEncoding>
                                    <channelsEndianess type="string">Big Endian</channelsEndianess>
                                    <fieldDominance type="int">2</fieldDominance>
                                    <height type="uint">1080</height>
                                    <nbChannels type="uint">3</nbChannels>
                                    <pixelLayout type="string">RGB</pixelLayout>
                                    <pixelRatio type="float">1</pixelRatio>
                                    <width type="uint">1920</width>
                                </storageFormat>
                                <sampleRate type="rate" version="4">
                                    <numerator>24000</numerator>
                                    <denominator>1001</denominator>
                                </sampleRate>
                                <spans type="spans" version="4">
                                    <span type="span" version="4">
                                        <duration>170</duration>
                                        <path encoding="pattern">/mnt/projects/arizona_adventure/sequences/Mirage/mi001/editorial/dpx_plates/v000/F004_C003_0228F8/F004_C003_0228F8_mi001.v000.[0100-0269].dpx</path>
                                    </span>
                                </spans>
                            </feed>
                            <feed type="feed" vuid="v001" uid="DA62F3A2-BA3B-4939-8089-EC7FC602AC74">
                                <storageFormat type="format">
                                    <type>video</type>
                                    <channelsDepth type="uint">10</channelsDepth>
                                    <channelsEncoding type="string">Integer</channelsEncoding>
                                    <channelsEndianess type="string">Little Endian</channelsEndianess>
                                    <fieldDominance type="int">2</fieldDominance>
                                    <height type="uint">1080</height>
                                    <nbChannels type="uint">3</nbChannels>
                                    <pixelLayout type="string">RGB</pixelLayout>
                                    <pixelRatio type="float">1</pixelRatio>
                                    <rowOrdering type="string">down</rowOrdering>
                                    <width type="uint">1920</width>
                                </storageFormat>
                                <userData type="dict">
                                    <recordTimecode type="time" label="00:00:00+00">
                                        <rate type="rate">24</rate>
                                        <nbTicks>0</nbTicks>
                                        <dropMode>NDF</dropMode>
                                    </recordTimecode>
                                </userData>
                                <sampleRate type="rate" version="4">
                                    <numerator>24000</numerator>
                                    <denominator>1001</denominator>
                                </sampleRate>
                                <startTimecode type="time">
                                    <rate type="rate">24</rate>
                                    <nbTicks>1391414</nbTicks>
                                    <dropMode>NDF</dropMode>
                                </startTimecode>
                                <spans type="spans" version="4">
                                    <span type="span" version="4">
                                        <path encoding="pattern">/mnt/projects/arizona_adventure/sequences/Mirage/mi001/editorial/dpx_plates/v001/F004_C003_0228F8/F004_C003_0228F8_mi001.v001.[0100-0269].dpx</path>
                                    </span>
                                </spans>
                            </feed>
                        </feeds>
                    </track>
                </tracks>
                <versions type="versions" currentVersion="v002">
                    <version type="version" uid="v000">
                        <name>v000</name>
                        <creationDate>2014/12/09 22:22:48</creationDate>
                        <userData type="dict">
                            <batchSetup type="binary">/mnt/projects/arizona_adventure/sequences/Mirage/mi001/editorial/flame/batch/mi001.v000.batch</batchSetup>
                            <versionNumber type="uint64">0</versionNumber>
                        </userData>
                    </version>
                    <version type="version" uid="v001">
                        <name>v001</name>
                        <creationDate>2014/12/09 22:30:04</creationDate>
                        <userData type="dict">
                            <batchSetup type="binary">/mnt/projects/arizona_adventure/sequences/Mirage/mi001/editorial/flame/batch/mi001.v001.batch</batchSetup>
                            <versionNumber type="uint64">1</versionNumber>
                        </userData>
                    </version>
                </versions>
            </clip>

        :param item: The item being published
        """

        self.logger.info("Updating Flame clip file...")

        # get the clip path as processed during validate()
        flame_clip_path = item.properties["flame_clip_path"]

        # get a handle on the write node app, stored during accept()
        write_node_app = item.properties.get("sg_writenode_app")
        render_path_fields = None

        if not write_node_app:
            # If we don't have a writenode, we just parse the first frame of the
            # item's sequence path to get the start and end frames.
            publish_path_flame = _get_flame_frame_spec_from_path(
                item.properties["sequence_paths"][0]
            )

            if not publish_path_flame:
                raise Exception(
                    "Couldn't extract min and max frame from the published "
                    "sequence! Will not update Flame clip xml."
                )
        else:
            # each publish task is connected to a nuke write node instance. this
            # value was populated via the collector and verified during accept()
            write_node = item.properties["sg_writenode"]

            # get the fields from the work file
            render_path = write_node_app.get_node_render_path(write_node)
            render_template = write_node_app.get_node_render_template(write_node)
            render_path_fields = render_template.get_fields(render_path)
            publish_template = write_node_app.get_node_publish_template(write_node)

            # set up the sequence token to be Flame friendly
            # e.g. mi001_scene_output_v001.[0100-0150].dpx
            # note - we cannot take the frame ranges from the write node -
            # because those values indicate the intended frame range rather
            # than the rendered frame range! In order for Flame to pick up
            # the media properly, it needs to contain the actual frame data

            # get all paths for all frames and all eyes
            paths = self.parent.sgtk.paths_from_template(
                publish_template,
                render_path_fields,
                skip_keys=["SEQ", "eye"]
            )

            # for each of them, extract the frame number. Track the min and the max.
            # TODO: would be nice to have a convenience method in core for this.
            min_frame = None
            max_frame = None
            for path in paths:
                fields = publish_template.get_fields(path)
                frame_number = fields["SEQ"]
                if min_frame is None or frame_number < min_frame:
                    min_frame = frame_number
                if max_frame is None or frame_number > max_frame:
                    max_frame = frame_number

            # ensure we have a min/max frame
            if min_frame is None or max_frame is None:
                raise Exception(
                    "Couldn't extract min and max frame from the published "
                    "sequence! Will not update Flame clip xml."
                )

            # now when we have the real min/max frame, we can apply a proper
            # sequence marker for the Flame xml. Note that we cannot use the normal
            # FORMAT: token in the template system, because the Flame frame format
            # is not totally "abstract" (e.g. %04d, ####, etc) but contains the
            # frame ranges themselves.
            #
            # the format spec is something like "04"
            sequence_key = publish_template.keys["SEQ"]

            # now compose the format string, eg. [%04d-%04d]
            format_str = "[%%%sd-%%%sd]" % (
                sequence_key.format_spec,
                sequence_key.format_spec
            )

            # and lastly plug in the values
            render_path_fields["SEQ"] = format_str % (min_frame, max_frame)

            # contruct the final path - because flame doesn't have any windows
            # support and because the "hub" platform is always linux (with potential
            # flame assist and flare satellite setups on macosx), request that the
            # paths are written out on linux form regardless of the operating system
            # currently running.
            publish_path_flame = publish_template.apply_fields(
                render_path_fields,
                "linux2"
            )

        # open up and update our xml file
        self.logger.debug("Parsing clip file: %s" % flame_clip_path)
        xml = minidom.parse(flame_clip_path)

        # We need to find the first video track. We do that by getting all of
        # the tracks:
        #
        #   <track type="track" uid="video">
        #       <trackType>video</trackType>
        #
        # We then look at the trackType element within, looking for a type
        # of "video". When we find one, we break out and move on.
        first_video_track = None

        for track in xml.getElementsByTagName("track"):
            for track_type in track.getElementsByTagName("trackType"):
                if "video" in [c.nodeValue for c in track_type.childNodes]:
                    first_video_track = track
                    break
            if first_video_track is not None:
                break

        if first_video_track is None:
            raise Exception(
                "Could not find the first video track in the published clip file!")

        clip_version = None
        for span in xml.getElementsByTagName("spans"):
            span_version = span.attributes.get("version")
            if span_version is not None:
                clip_version = span_version.value
            if clip_version is not None:
                break

        # For backwards compatibility's sake, we default to version 4.
        # For a long time, we just hardcoded this to 4, so it makes
        # sense to default to it here.
        clip_version = clip_version or "4"

        # now contruct our feed xml chunk we want to insert
        #
        # this is the xml structure we want to insert:
        #
        # <feed type="feed" vuid="%s" uid="%s">
        #     <spans type="spans" version="4">
        #         <span type="span" version="4">
        #             <path encoding="pattern">%s</path>
        #         </span>
        #     </spans>
        # </feed>
        unique_id = str(uuid.uuid4())

        # <feed type="feed" vuid="%s" uid="%s">
        feed_node = xml.createElement("feed")
        feed_node.setAttribute("type", "feed")
        feed_node.setAttribute("uid", unique_id)
        feed_node.setAttribute("vuid", unique_id)

        # <spans type="spans" version="4">
        spans_node = xml.createElement("spans")
        spans_node.setAttribute("type", "spans")
        spans_node.setAttribute("version", clip_version)
        feed_node.appendChild(spans_node)

        # <span type="span" version="4">
        span_node = xml.createElement("span")
        span_node.setAttribute("type", "span")
        span_node.setAttribute("version", clip_version)
        spans_node.appendChild(span_node)

        # <path encoding="pattern">%s</path>
        path_node = xml.createElement("path")
        path_node.setAttribute("encoding", "pattern")
        path_node.appendChild(xml.createTextNode(publish_path_flame))
        span_node.appendChild(path_node)

        # add new feed to first list of feeds inside of our track
        first_video_track.getElementsByTagName("feeds")[0].appendChild(
            feed_node
        )

        # now add same to the versions structure
        #
        # <version type="version" uid="%s">
        #     <name>%s</name>
        #     <creationDate>%s</creationDate>
        #     <userData type="dict">
        #     </userData>
        # </version>
        date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted_name = _generate_flame_clip_name(
            item,
            render_path_fields,
        )

        # <version type="version" uid="%s">
        version_node = xml.createElement("version")
        version_node.setAttribute("type", "version")
        version_node.setAttribute("uid", unique_id)

        # <name>v003 Comp</name>
        child_node = xml.createElement("name")
        child_node.appendChild(xml.createTextNode(formatted_name))
        version_node.appendChild(child_node)

        # <creationDate>1229-12-12 12:12:12</creationDate>
        child_node = xml.createElement("creationDate")
        child_node.appendChild(xml.createTextNode(date_str))
        version_node.appendChild(child_node)

        # <userData type="dict">
        child_node = xml.createElement("userData")
        child_node.setAttribute("type", "dict")
        version_node.appendChild(child_node)

        # add new feed to first list of versions
        xml.getElementsByTagName("versions")[0].appendChild(version_node)
        xml_string = xml.toxml(encoding="UTF-8")

        # make a backup of the clip file before we update it
        #
        # note - we are not using the template system here for simplicity
        # (user requiring customization can always modify this hook code
        # themselves). There is a potential edge case where the backup file
        # cannot be written at this point because you are on a different machine
        # or running with different permissions.
        backup_path = "%s.bak_%s" % (
            flame_clip_path,
            datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        )

        try:
            shutil.copy(flame_clip_path, backup_path)
        except Exception, e:
            raise Exception(
                "Failed to create a backup copy of the Flame clip file '%s': "
                "%s" % (flame_clip_path, e)
            )

        fh = open(flame_clip_path, "wt")
        try:
            fh.write(xml_string)
        finally:
            fh.close()

        # Finally, we create a new version of the clip's PublishedFile
        # if we have one associated with this item.
        self._version_up_clip_publish(item)

    def _version_up_clip_publish(self, item):
        """
        Attempts to create a new version of the PublishedFile that's associated
        clip that's associated with the given item. If there is no publish
        associated with the item's clip, nothing will happen. If the creation
        of the new publish fails, a warning will be logged but no exception
        will be raised. A failure to version up the clip's publish does not
        have a direct negative impact on the Flame<->Nuke workflow, so we won't
        allow it to stop the publish entirely.

        :param item: The item being published.
        """
        flame_clip_publish = item.properties.get("flame_clip_publish")
        if flame_clip_publish is None:
            return

        try:
            new_publish = register_publish(
                self.parent.sgtk,
                item.context,
                item.properties["flame_clip_path"],
                flame_clip_publish["name"],
                flame_clip_publish["version_number"] + 1,
                published_file_type=CLIP_PUBLISH_TYPE,
                comment=flame_clip_publish["description"],
            )
            self.logger.debug("New clip publish created: %s" % new_publish)
        except Exception as exc:
            self.logger.warning(
                "Failed to version up the clip's associated publish. This "
                "will not stop this publish from continuing, as the clip "
                "file itself was successfully updated, but the following "
                "exception must be addressed before versioning up the clip's "
                "publish is possible: %s" % exc
            )


def _get_flame_frame_spec_from_path(path):
    """
    Parses the file name in an attempt to determine the first and last
    frame number of a sequence. This assumes some sort of common convention
    for the file names, where the frame number is an integer at the end of
    the basename, just ahead of the file extension, such as
    file.0001.jpg, or file_001.jpg. We also check for input file names with
    abstracted frame number tokens, such as file.####.jpg, or file.%04d.jpg.
    Once the start and end frames have been extracted, this is used to build
    a frame-spec path, such as "/project/foo.[0001-0010].jpg".

    :param str path: The file path to parse.

    :returns: If the path can be parsed, a string path replacing the frame
        number with a frame range spec is returned.
    :rtype: str or None
    """
    # This pattern will match the following at the end of a string and
    # retain the frame number or frame token as group(1) in the resulting
    # match object:
    #
    # 0001
    # ####
    # %04d
    #
    # The number of digits or hashes does not matter; we match as many as
    # exist.
    frame_pattern = re.compile(r"^(.+?)([0-9#]+|[%]0\dd)$")
    root, ext = os.path.splitext(path)

    # NOTE:
    #   match.group(0) is the entire path.
    #   match.group(1) is everything up to the frame number.
    #   match.group(2) is the frame number.
    match = re.search(frame_pattern, root)

    # If we did not match, we don't know how to parse the file name, or there
    # is no frame number to extract.
    if not match:
        return None

    # We need to get all files that match the pattern from disk so that we
    # can determine what the min and max frame number is. We replace the
    # frame number or token with a * wildcard.
    glob_path = "%s%s" % (
        re.sub(match.group(2), "*", root),
        ext,
    )
    files = glob.glob(glob_path)

    # Our pattern from above matches against the file root, so we need
    # to chop off the extension at the end.
    file_roots = [os.path.splitext(f)[0] for f in files]

    # We know that the search will result in a match at this point, otherwise
    # the glob wouldn't have found the file. We can search and pull group 2
    # to get the integer frame number from the file root name.
    frame_padding = len(re.search(frame_pattern, file_roots[0]).group(2))
    frames = [int(re.search(frame_pattern, f).group(2)) for f in file_roots]
    min_frame = min(frames)
    max_frame = max(frames)

    # Turn that into something like "[%04d-%04d]"
    format_str = "[%%0%sd-%%0%sd]" % (
        frame_padding,
        frame_padding
    )

    # We end up with something like the following:
    #
    #    /project/foo.[0001-0010].jpg
    #
    frame_spec = format_str % (min_frame, max_frame)
    return "%s%s%s" % (match.group(1), frame_spec, ext)


def _generate_flame_clip_name(item, publish_fields):
    """
    Generates a name which will be displayed in the dropdown in Flame.

    :param item: The publish item being processed.
    :param publish_fields: Publish fields
    :returns: name string
    """

    # this implementation generates names on the following form:
    #
    # Comp, scene.nk (output background), v023
    # Comp, Nuke, v023
    # Lighting CBBs, final.nk, v034
    #
    # (depending on what pieces are available in context and names, names
    # may vary)

    context = item.context
    name = ""

    # If we have template fields passed in, then we'll try to extract
    # some information from them. If we don't, then we fall back on
    # some defaults worked out below.
    publish_fields = publish_fields or dict()

    # the shot will already be implied by the clip inside Flame (the clip
    # file which we are updating is a per-shot file. But if the context
    # contains a task or a step, we can display that:
    if context.task:
        name += "%s, " % context.task["name"].capitalize()
    elif context.step:
        name += "%s, " % context.step["name"].capitalize()

    # If we have a channel set for the write node or a name for the scene,
    # add those. If we don't have a name from the template fields, then we
    # fall back on the file sequence's basename without the extension or
    # frame number on the end (if possible).
    default_name, _ = os.path.splitext(
        os.path.basename(item.properties["sequence_paths"][0])
    )

    # Strips numbers off the end of the file name, plus any underscore or
    # . characters right before it.
    #
    # foo.1234 -> foo
    # foo1234  -> foo
    # foo_1234 -> foo
    default_name = re.sub(r"[._]*\d+$", "", default_name)
    rp_name = publish_fields.get("name", default_name,)
    rp_channel = publish_fields.get("channel")

    if rp_name and rp_channel:
        name += "%s.nk (output %s), " % (rp_name, rp_channel)
    elif not rp_name:
        name += "Nuke output %s, " % rp_channel
    elif not rp_channel:
        name += "%s.nk, " % rp_name
    else:
        name += "Nuke, "

    # Do our best to get a usable version number. If we have data extracted
    # using a template, we use that. If we don't, then we can look to see
    # if this publish item came with a clip PublishedFile, in which case
    # we use the version_number field from that entity +1, as a new version
    # of that published clip will be created as part of this update process,
    # and that is what we want to associate ourselves with here.
    version = publish_fields.get("version")

    if version is None and "flame_clip_publish" in item.properties:
        version = item.properties["flame_clip_publish"]["version_number"] + 1

    version = version or 0
    name += "v%03d" % version

    return name






