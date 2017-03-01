# Copyright (c) 2017 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import glob
import os
import re
import sys

from sgtk.platform import SoftwareLauncher, SoftwareVersion


def _template_to_product_name(template):
    """
    Converts a display name template name to a product name.

    For example, "NukeX %s Non-commercial" becomes "NukeX Non-commercial".
    """
    return template.replace("%s", "").replace("  ", " ").strip()


def _format(template, tokens):
    """
    Super dumb implementation of Python 2.6-like str.format.

    :param str template: String using {<name>} tokens for substitution.
    :param dict tokens: Dictionary of <name> to substitute for <value>.

    :returns: The substituted string, when "<name>" will yield "<value>".
    """
    for key, value in tokens.iteritems():
        template = template.replace("{%s}" % key, value)
    return template


class NukeLauncher(SoftwareLauncher):
    """
    Handles launching Nuke executables. Automatically starts up a tk-nuke
    engine with the current context in the new session of Nuke.
    """

    # Named regex strings to insert into the executable template paths when
    # matching against supplied versions and variants. Similar to the glob
    # strings, these allow us to alter the regex matching for any of the
    # variable components of the path in one place

    COMPONENT_REGEX_LOOKUP = {
        "version": r"(?P<version>[\d.v]+)",
        "variant": r"(?P<variant>[\w\s]+)",
        "suffix": r"(?P<suffix> Non-commercial| PLE){0,1}",
        # The Version is present twice on mac in the file path, so the second time
        # we simply reuse the value from the first match.
        "version_back": r"(?P=version)",
        "major_minor_version": r"(?P<major_minor_version>[\d.]+)"
    }

    # Templates for all the display names of the products supported by Nuke 7 and 8.
    NUKE_7_8_PRODUCT_DISPLAY_NAME_TEMPLATES = [
        "Nuke %s",
        "NukeX %s",
        "Nuke %s PLE",
        "NukeAssist %s",
    ]

    # Name of all the products supported by Nuke 7 and 8.
    NUKE_7_8_PRODUCTS = [
        _template_to_product_name(x) for x in NUKE_7_8_PRODUCT_DISPLAY_NAME_TEMPLATES
    ]

    # Templates for all the display names of the products supported by Nuke 9 and onward.
    NUKE_9_OR_HIGHER_PRODUCT_DISPLAY_NAME_TEMPLATES = [
        "Nuke %s",
        "Nuke %s Non-commercial",
        "NukeAssist %s",
        "NukeStudio %s",
        "NukeStudio %s Non-commercial",
        "NukeX %s",
        "NukeX %s Non-commercial",
        "Hiero %s"
    ]

    # Name for all the products supported by Nuke 9 and onward.
    NUKE_9_OR_HIGHER_PRODUCTS = [
        _template_to_product_name(x) for x in NUKE_9_OR_HIGHER_PRODUCT_DISPLAY_NAME_TEMPLATES
    ]

    # This dictionary defines a list of executable template strings for each
    # of the supported operating systems. The templates can are used for both
    # globbing and regex matches by replacing the named format placeholders
    # with an appropriate glob or regex string. As Side FX adds modifies the
    # install path on a given OS for a new release, a new template will need
    # to be added here.
    EXECUTABLE_MATCH_TEMPLATES = {
        "darwin": [
            # /Applications/Nuke10.0v5/NukeStudio10.0v5.app
            "/Applications/Nuke{version}/{variant}{version_back}{suffix}.app",
        ],
        "win32": [
            # C:\Program Files\Nuke10.0v5\Nuke10.0.exe
            "C:/Program Files/Nuke{version}/Nuke{major_minor_version}.exe",
        ],
        "linux2": [
            # /usr/local/Nuke10.0v5/Nuke10.0
            "/usr/local/Nuke{version}/Nuke{major_minor_version}",
            # /home/<username>/Nuke10.0v5/Nuke10.0
            os.path.expanduser("~/Nuke{version}/Nuke{major_minor_version}")
        ]
    }

    def _get_icon_from_product(self, product):
        """
        Returns the icon based on the product.

        :param str product: Product name.

        :returns: Path to the product's icon.
        """
        if "studio" in product.lower():
            return os.path.join(
                self.disk_location,
                "icon_nukestudio_256.png"
            )
        elif "hiero" in product.lower():
            return os.path.join(
                self.disk_location,
                "icon_hiero_256.png"
            )
        elif "nukex" in product.lower():
            return os.path.join(
                self.disk_location,
                "icon_x_256.png"
            )
        else:
            return os.path.join(
                self.disk_location,
                "icon_256.png"
            )

    def _find_executables(self, match_templates):
        """
        Finds all the executables available for this platform.

        :param list match_templates: List of Glob patterns that can match Nuke executables.

        :returns: Dictionary of results where the glob pattern is the key and the value
            is the files found with said pattern.
        """

        # build up a dictionary where the key is the match template and the
        # value is a list of matching executables. we'll need to keep the
        # association between template and matches for later when we extract
        # the components (version and product)
        executable_matches = {}
        for match_template in match_templates:

            # build the glob pattern by formatting the template for globbing
            glob_pattern = _format(match_template, dict((key, "*") for key in self.COMPONENT_REGEX_LOOKUP))
            self.logger.debug(
                "Globbing for executable matching: %s ..." % (glob_pattern,)
            )
            matching_paths = glob.glob(glob_pattern)
            if matching_paths:
                # found matches, remember this association (template: matches)
                executable_matches[match_template] = [x.replace("\\", "/") for x in matching_paths]
                self.logger.debug(
                    "Found %s matches: %s" % (
                        len(matching_paths),
                        matching_paths
                    )
                )

        return executable_matches

    def _find_products(self):
        """
        For each software executable that was found, get the software products for it.

        :returns: Generator that will iterate on each SoftwareVersion that was found.
        """
        executable_matches = self._find_executables(self.EXECUTABLE_MATCH_TEMPLATES[sys.platform])

        # now that we have a list of matching executables on disk and the
        # corresponding template used to find them, we can extract the component
        # pieces to see if they match the supplied version/variant constraints
        for (match_template, executable_paths) in executable_matches.iteritems():

            # construct the regex string to extract the components
            regex_pattern = _format(match_template, self.COMPONENT_REGEX_LOOKUP)

            # accumulate the software version objects to return. this will include
            # include the head/tail anchors in the regex
            regex_pattern = "^%s$" % (regex_pattern,)

            self.logger.debug(
                "Now matching components with regex: %s" % (regex_pattern,)
            )

            # compile the regex
            executable_regex = re.compile(regex_pattern, re.IGNORECASE)

            # iterate over each executable found for the glob pattern and find
            # matched components via the regex
            for executable_path in executable_paths:

                self.logger.debug("Processing path: %s" % (executable_path,))

                match = executable_regex.match(executable_path)

                if not match:
                    self.logger.debug("Path did not match regex.")
                    continue

                for product in self._extract_products_from_path(executable_path, match.groupdict()):
                    yield product

    def _extract_products_from_path(self, executable_path, match):
        """
        Extracts the products from an executable. Note that more than one product
        can be extracted from a single executable on certain platforms.

        :param str executable_path: Path to the executable.
        :param match: Tokens that were extracted from the executable.

        :returns: Generator that generates each product that can be launched from the given
            executable.
        """
        executable_version = match.get("version")
        if sys.platform == "darwin":
            # Extract the product from the file path, as each product of the product has an actual
            # executable associated to it.

            # extract the components (default to None if not included)
            executable_variant = match.get("variant")
            # If there is no suffix (Non-commercial or PLE), we'll simply use an empty string).
            executable_suffix = match.get("suffix") or ""

            # Generate the display name.
            display_name = "%s %s%s" % (executable_variant, executable_version, executable_suffix)

            yield SoftwareVersion(
                executable_version,
                executable_variant,
                display_name,
                executable_path,
                self._get_icon_from_product(executable_variant)
            )
        else:
            for product_template in self._get_product_templates_from_version(executable_version):

                # Figure out the arguments required for each product.
                arguments = []
                if "Studio" in product_template:
                    arguments.append("--studio")
                elif "Assist" in product_template:
                    arguments.append("--nukeassist")
                elif "NukeX" in product_template:
                    arguments.append("--nukex")
                elif "Hiero" in product_template:
                    arguments.append("--hiero")
                elif "PLE" in product_template:
                    arguments.append("--ple")

                # If this is a non-commercial build, we need to add the special argument.
                if "Non-commercial" in product_template:
                    arguments.append("--nc")

                executable_variant = product_template % (executable_version,)
                yield SoftwareVersion(
                    executable_version,
                    _template_to_product_name(product_template),
                    executable_variant,
                    executable_path,
                    self._get_icon_from_product(executable_variant),
                    arguments
                )

    def _get_product_templates_from_version(self, version):
        """
        Get the product templates for a given product version.

        :param str version: Nuke version in the format <Major>.<Minor>v<Patch>

        :returns: List of templates for the display names of the products.
        """
        # As of Nuke 6, Nuke versions formatting is <Major>.<Minor>v<Patch>.
        # This will grab the major version.
        if version.split(".", 1)[0] in ["7", "8"]:
            return self.NUKE_7_8_PRODUCT_DISPLAY_NAME_TEMPLATES
        else:
            return self.NUKE_9_OR_HIGHER_PRODUCT_DISPLAY_NAME_TEMPLATES

    def _get_products_from_version(self, version):
        """
        Get the name of the products for a given Nuke version.

        :param str version: Nuke version in the format <Major>.<Minor>v<Patch>

        :returns: List of product names.
        """
        # As of Nuke 6, Nuke versions formatting is <Major>.<Minor>v<patch>.
        # This will grab the major version.
        if version.split(".", 1)[0] in ["7", "8"]:
            return self.NUKE_7_8_PRODUCTS
        else:
            return self.NUKE_9_OR_HIGHER_PRODUCTS

    def scan_software(self):
        """
        Performs a scan for software installations.

        :param list versions: List of strings representing versions to search
            for. If set to None, search for all versions.

        :returns: List of :class:`SoftwareVersion` instances
        """
        self.logger.debug("Scanning for Nuke versions...")

        if sys.platform not in ["darwin", "win32", "linux2"]:
            self.logger.debug("Nuke not supported on platform %s.", sys.platform)
            return []

        software_versions = []
        for software_version in self._find_products():
            if self.is_version_supported(software_version):
                self.logger.debug("Accepting %s", software_version)
                software_versions.append(software_version)

        return software_versions

    def is_version_supported(self, version):
        """
        Ensures that a product is supported by the launcher and that the version is valid.

        :param version: Checks is a given software version is supported.
        :type version: :class:`sgtk.platform.SoftwareVersion`
        """
        return (
            # Make sure this is a product the software entity requested
            super(NukeLauncher, self).is_version_supported(version) and
            # And this is a product that Toolkit support. For example, HieroPlayer is not
            # supported.
            version.product in self._get_products_from_version(version.version)
        )

    @property
    def minimum_supported_version(self):
        """
        Minimum supported version by this launcher.

        As of February 2017, the earliest you can get a license from The Foundry is 7.0.
        """
        return "7.0v0"

    def prepare_launch(self, exec_path, args, file_to_open=None):
        """
        Prepares the given software for launch

        :param str exec_path: Path to DCC executable to launch

        :param str args: Command line arguments as strings

        :param str file_to_open: (optional) Full path name of a file to open on
            launch

        :returns: :class:`LaunchInformation` instance
        """
        pass
