# -*- coding: utf-8 -*-

###############################################################################

import threading

import xbmc
import xbmcgui
import xbmcaddon
import xbmcvfs

import utils
import downloadutils

import PlexAPI

###############################################################################


@utils.logging
@utils.ThreadMethods
class UserClient(threading.Thread):

    # Borg - multiple instances, shared state
    __shared_state = {}

    auth = True
    retry = 0

    currUser = None
    currUserId = None
    currServer = None
    currToken = None
    HasAccess = True
    AdditionalUser = []

    userSettings = None

    def __init__(self):

        self.__dict__ = self.__shared_state
        self.addon = xbmcaddon.Addon()

        self.doUtils = downloadutils.DownloadUtils()

        threading.Thread.__init__(self)

    def getAdditionalUsers(self):

        additionalUsers = utils.settings('additionalUsers')

        if additionalUsers:
            self.AdditionalUser = additionalUsers.split(',')

    def getUsername(self):

        username = utils.settings('username')

        if not username:
            self.logMsg("No username saved.", 2)
            return ""

        return username

    def getLogLevel(self):

        try:
            logLevel = int(utils.settings('logLevel'))
        except ValueError:
            logLevel = 0

        return logLevel

    def getUserId(self):

        log = self.logMsg
        window = utils.window
        settings = utils.settings

        username = self.getUsername()
        w_userId = window('emby_currUser')
        s_userId = settings('userId%s' % username)

        # Verify the window property
        if w_userId:
            if not s_userId:
                # Save access token if it's missing from settings
                settings('userId%s' % username, value=w_userId)
            log("Returning userId from WINDOW for username: %s UserId: %s"
                % (username, w_userId), 2)
            return w_userId
        # Verify the settings
        elif s_userId:
            log("Returning userId from SETTINGS for username: %s userId: %s"
                % (username, s_userId), 2)
            return s_userId
        # No userId found
        else:
            log("No userId saved for username: %s." % username, 1)

    def getServer(self, prefix=True):

        settings = utils.settings

        alternate = settings('altip') == "true"
        if alternate:
            # Alternate host
            HTTPS = settings('secondhttps') == "true"
            host = settings('secondipaddress')
            port = settings('secondport')
        else:
            # Original host
            HTTPS = settings('https') == "true"
            host = settings('ipaddress')
            port = settings('port')

        server = host + ":" + port

        if not host:
            self.logMsg("No server information saved.", 2)
            return False

        # If https is true
        if prefix and HTTPS:
            server = "https://%s" % server
            return server
        # If https is false
        elif prefix and not HTTPS:
            server = "http://%s" % server
            return server
        # If only the host:port is required
        elif not prefix:
            return server

    def getToken(self):

        log = self.logMsg
        window = utils.window
        settings = utils.settings

        username = self.getUsername()
        userId = self.getUserId()
        w_token = window('emby_accessToken%s' % userId)
        s_token = settings('accessToken')

        # Verify the window property
        if w_token:
            if not s_token:
                # Save access token if it's missing from settings
                settings('accessToken', value=w_token)
            log("Returning accessToken from WINDOW for username: %s accessToken: %s"
                % (username, w_token), 2)
            return w_token
        # Verify the settings
        elif s_token:
            log("Returning accessToken from SETTINGS for username: %s accessToken: %s"
                % (username, s_token), 2)
            window('emby_accessToken%s' % username, value=s_token)
            return s_token
        else:
            log("No token found.", 1)
            return ""

    def getSSLverify(self):
        # Verify host certificate
        settings = utils.settings

        s_sslverify = settings('sslverify')
        if settings('altip') == "true":
            s_sslverify = settings('secondsslverify')

        if s_sslverify == "true":
            return True
        else:
            return False

    def getSSL(self):
        # Client side certificate
        settings = utils.settings

        s_cert = settings('sslcert')
        if settings('altip') == "true":
            s_cert = settings('secondsslcert')

        if s_cert == "None":
            return None
        else:
            return s_cert

    def setUserPref(self):

        url = PlexAPI.PlexAPI().GetUserArtworkURL(self.currUser)
        if url:
            utils.window('EmbyUserImage', value=url)
        # Set resume point max
        # url = "{server}/emby/System/Configuration?format=json"
        # result = doUtils.downloadUrl(url)

        # utils.settings('markPlayed', value=str(result['MaxResumePct']))

    def getPublicUsers(self):

        server = self.getServer()

        # Get public Users
        url = "%s/emby/Users/Public?format=json" % server
        result = self.doUtils.downloadUrl(url, authenticate=False)

        if result != "":
            return result
        else:
            # Server connection failed
            return False

    def hasAccess(self):
        # Plex: always return True for now
        return True
        # hasAccess is verified in service.py
        log = self.logMsg
        window = utils.window

        url = "{server}/emby/Users?format=json"
        result = self.doUtils.downloadUrl(url)

        if result == False:
            # Access is restricted, set in downloadutils.py via exception
            log("Access is restricted.", 1)
            self.HasAccess = False

        elif window('emby_online') != "true":
            # Server connection failed
            pass

        elif window('emby_serverStatus') == "restricted":
            log("Access is granted.", 1)
            self.HasAccess = True
            window('emby_serverStatus', clear=True)
            xbmcgui.Dialog().notification("Emby for Kodi", utils.language(33007))

    def loadCurrUser(self, authenticated=False):

        window = utils.window

        doUtils = self.doUtils
        username = self.getUsername()
        userId = self.getUserId()

        # Only to be used if token exists
        self.currUserId = userId
        self.currServer = self.getServer()
        self.currToken = self.getToken()
        self.machineIdentifier = utils.settings('plex_machineIdentifier')
        self.ssl = self.getSSLverify()
        self.sslcert = self.getSSL()

        # Test the validity of current token
        if authenticated is False:
            url = "%s/clients" % (self.currServer)
            window('emby_currUser', value=userId)
            window('plex_username', value=username)
            window('emby_accessToken%s' % userId, value=self.currToken)
            result = doUtils.downloadUrl(url)

            if result == 401:
                # Token is no longer valid
                self.resetClient()
                return False

        # Set to windows property
        window('emby_currUser', value=userId)
        window('plex_username', value=username)
        window('emby_accessToken%s' % userId, value=self.currToken)
        window('emby_server%s' % userId, value=self.currServer)
        window('emby_server_%s' % userId, value=self.getServer(prefix=False))
        window('plex_machineIdentifier', value=self.machineIdentifier)

        # Set DownloadUtils values
        doUtils.setUsername(username)
        doUtils.setUserId(self.currUserId)
        doUtils.setServer(self.currServer)
        doUtils.setToken(self.currToken)
        doUtils.setSSL(self.ssl, self.sslcert)
        # parental control - let's verify if access is restricted
        # self.hasAccess()

        # Start DownloadUtils session
        doUtils.startSession()
        self.getAdditionalUsers()
        # Set user preferences in settings
        self.currUser = username
        self.setUserPref()
        return True

    def authenticate(self):

        log = self.logMsg
        lang = utils.language
        window = utils.window
        settings = utils.settings
        dialog = xbmcgui.Dialog()

        # Get /profile/addon_data
        plx = PlexAPI.PlexAPI()
        addondir = xbmc.translatePath(self.addon.getAddonInfo('profile')).decode('utf-8')
        hasSettings = xbmcvfs.exists("%ssettings.xml" % addondir)

        username = self.getUsername()
        userId = settings('userId%s' % username)
        server = self.getServer()

        # If there's no settings.xml
        if not hasSettings:
            log("No settings.xml found.", 1)
            self.auth = False
            return
        # If no user information
        elif not server:
            log("Missing server information.", 0)
            self.auth = False
            return
        # If there's a token, load the user
        elif self.getToken():
            result = self.loadCurrUser()

            if result is False:
                pass
            else:
                log("Current user: %s" % self.currUser, 1)
                log("Current userId: %s" % self.currUserId, 1)
                log("Current accessToken: xxxx", 1)

                window('suspend_LibraryThread', clear=True)
                return

        # AUTHENTICATE USER #####
        # Choose Plex user login
        myplexlogin, plexhome, plexLogin, dont_use_accessToken = \
            plx.GetPlexLoginFromSettings()
        log("myplexlogin: %s, plexhome: %s, plexLogin: %s"
            % (myplexlogin, plexhome, plexLogin), 2)
        if myplexlogin == "true" and plexhome == 'true':
            username, userId, accessToken = plx.ChoosePlexHomeUser()
        else:
            log("Trying to connect to PMS without a token", 0)
            accessToken = ''
        # Check connection
        if plx.CheckConnection(server, accessToken) == 200:
            self.currUser = username
            dialog = xbmcgui.Dialog()
            if username:
                dialog.notification(
                    heading=self.addonName,
                    message="Welcome %s" % username.decode('utf-8'),
                    icon="special://home/addons/plugin.video.plexkodiconnect/icon.png")
            else:
                dialog.notification(
                    heading=self.addonName,
                    message="Welcome",
                    icon="special://home/addons/plugin.video.plexkodiconnect/icon.png")
            settings('accessToken', value=accessToken)
            settings('userId%s' % username, value=userId)
            log("User authenticated with an access token", 1)
            self.loadCurrUser(authenticated=True)
            window('emby_serverStatus', clear=True)
            # Write plex_machineIdentifier to window
            plex_machineIdentifier = settings('plex_machineIdentifier')
            window('plex_machineIdentifier', plex_machineIdentifier)
            self.retry = 0
            # Make sure that lib sync thread is not paused
            utils.window('suspend_LibraryThread', value='false')
        else:
            self.logMsg("Error: user authentication failed.", -1)
            settings('accessToken', value="")
            settings('userId%s' % username, value="")

            # Give 3 attempts at entering password / selecting user
            if self.retry == 3:
                log("Too many retries. You can retry by resetting attempts in "
                    "the addon settings.", 1)
                window('emby_serverStatus', value="Stop")
                dialog.ok(lang(33001), lang(33010))

            self.retry += 1
            self.auth = False

    def resetClient(self):
        self.logMsg("Reset UserClient authentication.", 1)
        username = self.getUsername()

        utils.settings('accessToken', value="")
        utils.window('emby_accessToken%s' % username, clear=True)
        self.currToken = None
        self.logMsg("User token has been removed.", 1)

        self.auth = True
        self.currUser = None

    def run(self):
        log = self.logMsg
        window = utils.window

        log("----===## Starting UserClient ##===----", 0)
        while not self.threadStopped():
            while self.threadSuspended():
                if self.threadStopped():
                    break
                xbmc.sleep(3000)

            status = window('emby_serverStatus')
            if status:
                # Verify the connection status to server
                if status == "restricted":
                    # Parental control is restricting access
                    self.HasAccess = False

                elif status == "401":
                    # Unauthorized access, revoke token
                    window('emby_serverStatus', value="Auth")
                    self.resetClient()

            if self.auth and (self.currUser is None):
                # Try to authenticate user
                status = window('emby_serverStatus')
                if not status or status == "Auth":
                    # Set auth flag because we no longer need
                    # to authenticate the user
                    self.auth = False
                    self.authenticate()

            if not self.auth and (self.currUser is None):
                # If authenticate failed.
                server = self.getServer()
                username = self.getUsername()
                status = window('emby_serverStatus')

                # The status Stop is for when user cancelled password dialog.
                if server and username and status != "Stop":
                    # Only if there's information found to login
                    log("Server found: %s" % server, 2)
                    log("Username found: %s" % username, 2)
                    self.auth = True

        self.doUtils.stopSession()
        log("##===---- UserClient Stopped ----===##", 0)
