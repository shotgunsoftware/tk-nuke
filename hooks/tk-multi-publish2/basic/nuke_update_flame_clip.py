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

import sgtk

from sgtk.util.shotgun.publish_util import get_published_file_entity_type
from sgtk.util.shotgun.publish_resolve import resolve_publish_path


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

        # Check to see if we have a template to use. In that case, the
        # we'll be trying to find a clip file that that location. If we
        # don't have a template configured, or the clip file doesn't
        # exist at that location on disk, we'll look for a published
        # clip.
        flame_clip_path = None
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
            publish_type = get_published_file_entity_type(publisher.sgtk)

            # TODO: Should we get and update all of the clips that might be
            # published? We're told this is an unlikely workflow by the Flame
            # team, but it's technically possible. It raises other concerns,
            # though, because then we have to ask the question of which (or all?)
            # clips should be updated, and how we'd know that programmatically.
            #
            # UPDATE: We're going to do a middle-ground approach. If there are
            # multiple clips, we're going to iterate over each one until we find
            # one that has a local_path that exists. Once we find that, we use it.
            # In most cases this will not do anything differently than the template
            # driven solution, because we'll have a single OpenClip published for
            # the shot, but there might be cases where this heads off a problem.
            clip_publish_types = ["Flame OpenClip", "Flame Batch OpenClip"]
            self.logger.debug("Clip publish types to search for: %s" % clip_publish_types)
            clip_publishes = publisher.shotgun.find(
                publish_type,
                [
                    ["entity", "is", item.context.entity],
                    ["published_file_type.PublishedFileType.code", "in", clip_publish_types],
                ],
                fields=("path",),
            )

            if clip_publishes:
                self.logger.debug("Found clip(s): %s" % clip_publishes)

            for clip_publish in clip_publishes:
                self.logger.debug("Checking existence of OpenClip: %s" % clip_publish)
                # flame_clip_path = clip_publish["path"].get("local_path")
                try:
                    flame_clip_path = resolve_publish_path(publisher.sgtk, clip_publish)
                except Exception:
                    self.logger.debug("Unable to resolve path: %s" % clip_publish)

                if flame_clip_path and os.path.exists(flame_clip_path):
                    self.logger.debug("Found usable OpenClip publish: %s" % flame_clip_path)
                    break
                else:
                    flame_clip_path = None
                    self.logger.debug("Published OpenClip isn't accessible: %s" % flame_clip_path)

            if not flame_clip_path:
                self.logger.debug("Unable to find a usable OpenClip publish.")

        if flame_clip_path and not os.path.exists(flame_clip_path):
            flame_clip_path = None
            self.logger.debug(
                "Unable to locate the Flame clip file on disk. Expected "
                "path is '%s'." % flame_clip_path
            )
        elif flame_clip_path:
            # We have a path and it exists.
            item.properties["flame_clip_path"] = flame_clip_path
        else:
            self.logger.debug(
                "No flame clip was found to update. "
                "Plugin %s not accepting item: %s" % (self, item)
            )

        return {"accepted": (flame_clip_path is not None)}

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

        # update shot clip xml file with this publish
        try:
            self._update_flame_clip(item)
        except Exception, e:
            raise("Unable to update Flame clip xml: %s" % (e,))

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

        # get a handle on the write node app, stored during accept()
        write_node_app = item.properties["sg_writenode_app"]

        # each publish task is connected to a nuke write node instance. this
        # value was populated via the collector and verified during accept()
        write_node = item.properties["sg_writenode"]

        # get the clip path as processed during validate()
        flame_clip_path = item.properties["flame_clip_path"]

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
        xml = minidom.parse(flame_clip_path)

        # find first <track type="track" uid="video">
        first_video_track = None
        for track in xml.getElementsByTagName("track"):
            if track.attributes["uid"].value == "video":
                first_video_track = track
                break

        if first_video_track is None:
            raise Exception(
                "Could not find <track type='track' uid='video'> in clip file!")

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
        spans_node.setAttribute("version", "4")
        feed_node.appendChild(spans_node)

        # <span type="span" version="4">
        span_node = xml.createElement("span")
        span_node.setAttribute("type", "span")
        span_node.setAttribute("version", "4")
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
            item.context,
            render_path_fields
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


def _generate_flame_clip_name(context, publish_fields):
    """
    Generates a name which will be displayed in the dropdown in Flame.

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

    name = ""

    # the shot will already be implied by the clip inside Flame (the clip
    # file which we are updating is a per-shot file. But if the context
    # contains a task or a step, we can display that:
    if context.task:
        name += "%s, " % context.task["name"].capitalize()
    elif context.step:
        name += "%s, " % context.step["name"].capitalize()

    # if we have a channel set for the write node or a name for the scene,
    # add those
    rp_name = publish_fields.get("name")
    rp_channel = publish_fields.get("channel")

    if rp_name and rp_channel:
        name += "%s.nk (output %s), " % (rp_name, rp_channel)
    elif not rp_name:
        name += "Nuke output %s, " % rp_channel
    elif not rp_channel:
        name += "%s.nk, " % rp_name
    else:
        name += "Nuke, "

    # and finish with version number
    name += "v%03d" % (publish_fields.get("version") or 0)

    return name
