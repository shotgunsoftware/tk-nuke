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
import sys
import sgtk
import contextlib
import pprint

from sgtk.platform import SoftwareLauncher, SoftwareVersion, LaunchInformation


class NukeLauncher(SoftwareLauncher):
    """
    Handles launching Nuke executables. Automatically starts up a tk-nuke
    engine with the current context in the new session of Nuke.
    """

    # Named regex strings to insert into the executable template paths when
    # matching against supplied versions and products. Similar to the glob
    # strings, these allow us to alter the regex matching for any of the
    # variable components of the path in one place

    COMPONENT_REGEX_LOOKUP = {
        "version": r"[\d.v]+",
        "product": r"[A-Za-z]+",
        # The Version is present twice on mac in the file path, so the second time
        # we simply reuse the value from the first match.
        "version_back": r"[\d.v]+",
        "major_minor_version": r"[\d.]+"
    }

    # Templates for all the display names of the products supported by Nuke 7 and 8.
    NUKE_7_8_PRODUCTS = [
        "Nuke",
        "NukeX",
        "NukeAssist",
    ]

    # Templates for all the display names of the products supported by Nuke 9 and onward.
    NUKE_9_OR_HIGHER_PRODUCTS = [
        "Nuke",
        "NukeAssist",
        "NukeStudio",
        "NukeX",
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
            # Note that this regular expression will purposefully not match Nuke PLE and
            # Non-Commercial.
            "/Applications/Nuke{version}/{product}{version_back}.app",
        ],
        "win32": [
            # C:/Program Files/Nuke10.0v5/Nuke10.0.exe
            "C:\\Program Files\\Nuke{version}\\Nuke{major_minor_version}.exe",
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

    def scan_software(self):
        """
        For each software executable that was found, get the software products for it.

        :returns: List of :class:`SoftwareVersion`.
        """
        softwares = []
        self.logger.debug("Scanning for Nuke-based software.")
        for sw in self._find_software():
            supported, reason = self._is_supported(sw)
            if supported:
                softwares.append(sw)
            else:
                self.logger.debug(reason)

        return softwares

    def _find_software(self):
        """
        Finds all Nuke software on disk.

        :returns: Generator of :class:`SoftwareVersion`.
        """
        # Certain platforms have more than one location for installed software
        for template in self.EXECUTABLE_MATCH_TEMPLATES[sys.platform]:
            self.logger.debug("Processing template %s.", template)
            # Extract all products from that executable.
            for executable, tokens in self._glob_and_match(template, self.COMPONENT_REGEX_LOOKUP):
                self.logger.debug("Processing %s with tokens %s", executable, tokens)
                for sw in self._extract_products_from_path(executable, tokens):
                    yield sw

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
            executable_product = match.get("product")
            # If there is no suffix (Non-commercial or PLE), we'll simply use an empty string).
            executable_suffix = match.get("suffix") or ""

            # Generate the display name.
            product = "%s%s" % (executable_product, executable_suffix)

            yield SoftwareVersion(
                executable_version,
                product,
                executable_path,
                self._get_icon_from_product(executable_product)
            )
        else:
            for product in self._get_products_from_version(executable_version):
                # Figure out the arguments required for each product.
                arguments = []
                if "Studio" in product:
                    arguments.append("--studio")
                elif "Assist" in product:
                    arguments.append("--nukeassist")
                elif "NukeX" in product:
                    arguments.append("--nukex")
                elif "Hiero" in product:
                    arguments.append("--hiero")

                sw = SoftwareVersion(
                    executable_version,
                    product,
                    executable_path,
                    self._get_icon_from_product(product),
                    arguments
                )
                yield sw

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

    def _is_supported(self, version):
        """
        Ensures that a product is supported by the launcher and that the version is valid.

        :param version: Checks is a given software version is supported.
        :type version: :class:`sgtk.platform.SoftwareVersion`

        :returns: ``True`` if supported, ``False`` if not.
        """
        if version.product not in self._get_products_from_version(version.version):
            return False, "Toolkit does not support '%s'." % version.product

        return super(NukeLauncher, self)._is_supported(version)

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

        # Get the basic environment variables to launch Nuke. Do this by reusing Toolkit classic's
        # bootstrap code.
        startup_python_path = os.path.join(
            self.disk_location,
            "python",
            "startup"
        )

        with self.temporary_import(startup_python_path, "bootstrap") as bootstrap:
            launch_plugins = self.get_setting("launch_builtin_plugins")

            if launch_plugins:
                self.logger.info("Launch plugins: %s", launch_plugins)

                # Get Nuke environment for plugin launch.
                required_env, required_args = bootstrap.get_plugin_startup_env(
                    launch_plugins, exec_path, args, file_to_open
                )

                # Add std context and site info to the env.
                required_env.update(self.get_standard_plugin_environment())

                # Make sure we are picking the right engine.
                required_env["SHOTGUN_ENGINE"] = self.engine_name
            else:
                self.logger.info("Preparing Nuke Launch via Toolkit Classic methodology ...")

                # Get Nuke environment for Toolkit Classic launch.
                required_env, required_args = bootstrap.get_classic_startup_env(
                    exec_path, args, file_to_open
                )
                # Add context information info to the env.
                required_env["TANK_CONTEXT"] = sgtk.Context.serialize(self.context)
                required_env["TANK_ENGINE"] = self.engine_name

            self.logger.debug("Launch environment: %s", pprint.pformat(required_env))
            self.logger.debug("Launch arguments: %s", required_args)

        return LaunchInformation(exec_path, required_args, required_env)

    @contextlib.contextmanager
    def temporary_import(self, module_path, module_name):
        """
        Imports a module and ensures its path is removed and the module removed from
        sys.module when the scope is terminated.

        :param str module_path: Path to add to the ``sys.path`` before importing. Can be ``None``.
        :param str module_name: Name of the module to temporarily import.

        This method will yield the module that was imported temporarily.
        """
        try:
            if module_path:
                sys.path.insert(0, module_path)
            yield __import__(module_name)
        finally:
            if module_path:
                sys.path.remove(module_path)
            if module_name in sys.modules:
                del sys.modules[module_name]
