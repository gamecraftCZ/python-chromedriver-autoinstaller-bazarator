# coding: utf-8
"""
Helper functions for filename and URL generation.
"""

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as elemTree
import zipfile
from io import BytesIO
import platform as pf

__author__ = "Yeongbin Jo <iam.yeongbin.jo@gmail.com>"

from typing import AnyStr, Optional


def get_chromedriver_filename():
    """
    Returns the filename of the binary for the current platform.
    :return: Binary filename
    """
    if sys.platform.startswith("win"):
        return "chromedriver.exe"
    return "chromedriver"


def get_variable_separator():
    """
    Returns the environment variable separator for the current platform.
    :return: Environment variable separator
    """
    if sys.platform.startswith("win"):
        return ";"
    return ":"


def get_platform_architecture(chrome_version=None):
    if sys.platform.startswith("linux") and sys.maxsize > 2**32:
        platform = "linux"
        architecture = "64"
    elif sys.platform == "darwin":
        platform = "mac"
        # At some points, the release naming for Apple arm changed;
        # Looking in http://chromedriver.storage.googleapis.com/, the changeover happened across these releases:
        # 106.0.5249.61/chromedriver_mac_arm64.zip
        # 106.0.5249.21/chromedriver_mac64_m1.zip
        # Mac architecture naming changed again as of the transition to CfT
        # 115.0.5763.0/mac-arm64/chromedriver-mac-arm64.zip'
        # 115.0.5763.0/mac-x64/chromedriver-mac-x64.zip'
        if pf.processor() == "arm":
            if chrome_version is not None and chrome_version >= "115.0.5763.0":
                print("CHROME >= 115.0.5763.0, using mac-arm64 as architecture identifier")
                architecture = "-arm64"
            elif chrome_version is not None and chrome_version <= "106.0.5249.21":
                print("CHROME <= 106.0.5249.21, using mac64_m1 as architecture identifier")
                architecture = "64_m1"
            else:
                architecture = "_arm64"
        elif pf.processor() == "i386":
            if chrome_version is not None and chrome_version >= "115.0.5763.0":
                print("CHROME >= 115.0.5763.0, using mac-x64 as architecture identifier")
                architecture = "-x64"
            else:
                architecture = "mac64"
        else:
            raise RuntimeError("Could not determine Mac processor architecture.")
    elif sys.platform.startswith("win"):
        platform = "win"
        architecture = "32"
    else:
        raise RuntimeError(
            "Could not determine chromedriver download URL for this platform."
        )
    return platform, architecture


def get_chromedriver_url(chromedriver_version, no_ssl=False):
    """
    Generates the download URL for current platform , architecture and the given version.
    Supports Linux, MacOS and Windows.

    :param chromedriver_version: ChromeDriver version string
    :param no_ssl:               Whether to use the encryption protocol when downloading the chrome driver
    :return:                     String. Download URL for chromedriver
    """
    #return f"https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/{chromedriver_version}/win32/chromedriver-win32.zip"
    platform, architecture = get_platform_architecture(chromedriver_version)
    if chromedriver_version >= "115":  # new CfT ChromeDriver versions have their URLs published
        versions_url = "googlechromelabs.github.io/chrome-for-testing/known-good-versions-with-downloads.json"
        versions_url = "http://" + versions_url if no_ssl else "https://" + versions_url
        download_version_list = json.load(urllib.request.urlopen(versions_url))
        for good_version in download_version_list["versions"]:
            if good_version["version"] == chromedriver_version:
                download_urls = good_version["downloads"]["chromedriver"]
                for url in download_urls:
                    if url["platform"] == platform + architecture:
                        return url['url']
    else:  # old ChromeDriver versions use the old urls
        base_url = "chromedriver.storage.googleapis.com/"
        base_url = "http://" + base_url if no_ssl else "https://" + base_url
        return base_url + chromedriver_version + "/chromedriver_" + platform + architecture + ".zip"


def find_binary_in_path(filename):
    """
    Searches for a binary named `filename` in the current PATH. If an executable is found, its absolute path is returned
    else None.
    :param filename: Filename of the binary
    :return: Absolute path or None
    """
    if "PATH" not in os.environ:
        return None
    for directory in os.environ["PATH"].split(get_variable_separator()):
        binary = os.path.abspath(os.path.join(directory, filename))
        if os.path.isfile(binary) and os.access(binary, os.X_OK):
            return binary
    return None


def check_version(binary, required_version):
    try:
        version = subprocess.check_output([binary, "-v"])
        version = re.match(r".*?([\d.]+).*?", version.decode("utf-8"))[1]
        if version == required_version:
            return True
    except Exception:
        return False
    return False


def get_chrome_version():
    """
    :return: the version of chrome installed on client
    """
    platform, _ = get_platform_architecture()
    if platform == "linux":
        path = get_linux_executable_path()
        with subprocess.Popen([path, "--version"], stdout=subprocess.PIPE) as proc:
            version = (
                proc.stdout.read()
                .decode("utf-8")
                .replace("Chromium", "")
                .replace("Google Chrome", "")
                .strip()
            )
    elif platform == "mac":
        process = subprocess.Popen(
            [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "--version",
            ],
            stdout=subprocess.PIPE,
        )
        version = (
            process.communicate()[0]
            .decode("UTF-8")
            .replace("Google Chrome", "")
            .strip()
        )
    elif platform == "win":
        # check both of Program Files and Program Files (x86).
        # if the version isn't found on both of them, version is an empty string.
        dirs = [f.name for f in os.scandir("C:\\Program Files\\Google\\Chrome\\Application") if f.is_dir() and re.match("^[0-9.]+$", f.name)]
        if dirs:
            version = max(dirs)
        else:
            dirs = [f.name for f in os.scandir("C:\\Program Files (x86)\\Google\\Chrome\\Application") if f.is_dir() and re.match("^[0-9.]+$", f.name)]
            version = max(dirs) if dirs else ''
    else:
        return
    return version


def get_linux_executable_path():
    """
    Look through a list of candidates for Google Chrome executables that might
    exist, and return the full path to first one that does. Raise a ValueError
    if none do.

    :return: the full path to a Chrome executable on the system
    """
    for executable in (
        "google-chrome",
        "google-chrome-stable",
        "google-chrome-beta",
        "google-chrome-dev",
        "chromium-browser",
        "chromium",
    ):
        path = shutil.which(executable)
        if path is not None:
            return path
    raise ValueError("No chrome executable found on PATH")


def get_major_version(version):
    """
    :param version: the version of chrome
    :return: the major version of chrome
    """
    return version.split(".")[0]


def get_matched_chromedriver_version(chrome_version, no_ssl=False):
    """
    Try to find a specific version of ChromeDriver to match a version of cCrome

    :param chrome_version: the version of Chrome to match against
    :param no_ssl:         get version list using unsecured HTTP get
    :return:               String. The version of chromedriver that matches the Chrome version
                           None.   if no matching version of chromedriver was discovered
    """
    #return chrome_version
    # Newer versions of chrome use the CfT publishing system
    if chrome_version >= "115":
        version_url = "googlechromelabs.github.io/chrome-for-testing/known-good-versions.json"
        version_url = "http://" + version_url if no_ssl else "https://" + version_url
        good_version_list = json.load(urllib.request.urlopen(version_url))
        for good_version in good_version_list["versions"]:
            if good_version["version"] == chrome_version:
                return chrome_version
                
        # if no exact match found: use latest patch for the chrome build as fallback
        build = '.'.join(chrome_version.split('.')[:-1])
        builds_url = "googlechromelabs.github.io/chrome-for-testing/latest-patch-versions-per-build.json"
        builds_url = "http://" + builds_url if no_ssl else "https://" + builds_url
        build_list = json.load(urllib.request.urlopen(builds_url))
        entry = build_list["builds"][build]
        if entry: return entry["version"]
            
    # check old versions of chrome using the old system
    else:
        version_url = "chromedriver.storage.googleapis.com"
        version_url = "http://" + version_url if no_ssl else "https://" + version_url
        doc = urllib.request.urlopen(version_url).read()
        root = elemTree.fromstring(doc)
        for k in root.iter("{http://doc.s3.amazonaws.com/2006-03-01}Key"):
            if k.text.find(get_major_version(chrome_version) + ".") == 0:
                return k.text.split("/")[0]
    return


def get_chromedriver_path():
    """
    :return: path of the chromedriver binary
    """
    return os.path.abspath(os.path.dirname(__file__))


def print_chromedriver_path():
    """
    Print the path of the chromedriver binary.
    """
    print(get_chromedriver_path())


def download_chromedriver(path: Optional[AnyStr] = None, no_ssl: bool = False):
    """
    Downloads, unzips and installs chromedriver.
    If a chromedriver binary is found in PATH it will be copied, otherwise downloaded.

    :param str path: Path of the directory where to save the downloaded chromedriver to.
    :param bool no_ssl: Determines whether or not to use the encryption protocol when downloading the chrome driver.
    :return: The file path of chromedriver
    """
    chrome_version = get_chrome_version()
    if not chrome_version:
        logging.debug("Chrome is not installed.")
        return
    chromedriver_version = get_matched_chromedriver_version(chrome_version, no_ssl)
    if not chromedriver_version:
        logging.warning(
            "Can not find chromedriver for currently installed chrome version."
        )
        return
    major_version = get_major_version(chromedriver_version)

    if path:
        if not os.path.isdir(path):
            raise ValueError(f"Invalid path: {path}")
        chromedriver_dir = os.path.join(os.path.abspath(path), major_version)
    else:
        chromedriver_dir = os.path.join(
            os.path.abspath(os.path.dirname(__file__)), major_version
        )
    chromedriver_filename = get_chromedriver_filename()
    chromedriver_filepath = os.path.join(chromedriver_dir, chromedriver_filename)
    if not os.path.isfile(chromedriver_filepath) or not check_version(
        chromedriver_filepath, chromedriver_version
    ):
        logging.info(f"Downloading chromedriver ({chromedriver_version})...")
        if not os.path.isdir(chromedriver_dir):
            os.makedirs(chromedriver_dir)
        url = get_chromedriver_url(chromedriver_version=chromedriver_version, no_ssl=no_ssl)
        try:
            response = urllib.request.urlopen(url)
            if response.getcode() != 200:
                raise urllib.error.URLError("Not Found")
        except urllib.error.URLError:
            raise RuntimeError(f"Failed to download chromedriver archive: {url}")
        archive = BytesIO(response.read())
        with zipfile.ZipFile(archive) as zip_file:
            # v115+ have files in subdirectories- need to adjust filename before extracting
            for zip_info in zip_file.infolist():
                if os.path.basename(zip_info.filename) == chromedriver_filename:
                    zip_info.filename = chromedriver_filename
                    zip_file.extract(zip_info, chromedriver_dir)
                    break
    else:
        logging.info("Chromedriver is already installed.")
    if not os.access(chromedriver_filepath, os.X_OK):
        os.chmod(chromedriver_filepath, 0o744)
    return chromedriver_filepath


if __name__ == "__main__":
    print(get_chrome_version())
    print(download_chromedriver(no_ssl=False))
