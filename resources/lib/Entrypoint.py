import xbmcaddon
import xbmcplugin
import xbmc
import xbmcgui
import xbmcvfs
import os, sys
import threading
import json
import urllib
import time

WINDOW = xbmcgui.Window(10000)

import Utils as utils
from ClientInformation import ClientInformation
from PlaybackUtils import PlaybackUtils
from PlayUtils import PlayUtils
from DownloadUtils import DownloadUtils
from ReadEmbyDB import ReadEmbyDB
from API import API
from UserPreferences import UserPreferences


##### Play items via plugin://plugin.video.emby/ #####
def doPlayback(id):
    url = "{server}/mediabrowser/Users/{UserId}/Items/%s?format=json&ImageTypeLimit=1" % id
    result = DownloadUtils().downloadUrl(url)
    item = PlaybackUtils().PLAY(result, setup="default")


#### DO RESET AUTH #####    
def resetAuth():
    # User tried login and failed too many times
    resp = xbmcgui.Dialog().yesno("Warning", "Emby might lock your account if you fail to log in too many times. Proceed anyway?")
    if resp == 1:
        xbmc.log("Reset login attempts.")
        WINDOW.setProperty("Server_status", "Auth")
    else:
        xbmc.executebuiltin('Addon.OpenSettings(plugin.video.emby)')

### ADD ADDITIONAL USERS ###
def addUser():

    doUtils = DownloadUtils()
    clientInfo = ClientInformation()
    currUser = WINDOW.getProperty("currUser")
    deviceId = clientInfo.getMachineId()
    deviceName = clientInfo.getDeviceName()

    # Get session
    url = "{server}/mediabrowser/Sessions?DeviceId=%s" % deviceId
    result = doUtils.downloadUrl(url)
    
    try:
        sessionId = result[0][u'Id']
        additionalUsers = result[0][u'AdditionalUsers']
        # Add user to session
        userlist = {}
        users = []
        url = "{server}/mediabrowser/Users?IsDisabled=false&IsHidden=false"
        result = doUtils.downloadUrl(url)

        # pull the list of users
        for user in result:
            name = user[u'Name']
            userId = user[u'Id']
            if currUser not in name:
                userlist[name] = userId
                users.append(name)

        # Display dialog if there's additional users
        if additionalUsers:

            option = xbmcgui.Dialog().select("Add/Remove user from the session", ["Add user", "Remove user"])
            # Users currently in the session
            additionalUserlist = {}
            additionalUsername = []
            # Users currently in the session
            for user in additionalUsers:
                name = user[u'UserName']
                userId = user[u'UserId']
                additionalUserlist[name] = userId
                additionalUsername.append(name)

            if option == 1:
                # User selected Remove user
                resp = xbmcgui.Dialog().select("Remove user from the session", additionalUsername)
                if resp > -1:
                    selected = additionalUsername[resp]
                    selected_userId = additionalUserlist[selected]
                    url = "{server}/mediabrowser/Sessions/%s/Users/%s" % (sessionId, selected_userId)
                    postdata = {}
                    doUtils.downloadUrl(url, postBody=postdata, type="DELETE")
                    xbmcgui.Dialog().notification("Success!", "%s removed from viewing session" % selected, time=1000)
                    return
                else:
                    return

            elif option == 0:
                # User selected Add user
                for adduser in additionalUsername:
                    xbmc.log(str(adduser))
                    users.remove(adduser)

            elif option < 0:
                # User cancelled
                return

        # Subtract any additional users
        xbmc.log("Displaying list of users: %s" % users)
        resp = xbmcgui.Dialog().select("Add user to the session", users)
        # post additional user
        if resp > -1:
            selected = users[resp]
            selected_userId = userlist[selected]
            url = "{server}/mediabrowser/Sessions/%s/Users/%s" % (sessionId, selected_userId)
            postdata = {}
            doUtils.downloadUrl(url, postBody=postdata, type="POST")
            xbmcgui.Dialog().notification("Success!", "%s added to viewing session" % selected, time=1000)

    except:
        xbmc.log("Failed to add user to session.")
        xbmcgui.Dialog().notification("Error", "Unable to add/remove user from the session.", xbmcgui.NOTIFICATION_ERROR)

# THEME MUSIC/VIDEOS
def getThemeMedia():

    doUtils = DownloadUtils()
    playUtils = PlayUtils()
    
    currUser = WINDOW.getProperty('currUser')
    server = WINDOW.getProperty('server%s' % currUser)
    playback = None

    library = xbmc.translatePath("special://profile/addon_data/plugin.video.emby/library/").decode('utf-8')

    # Choose playback method
    resp = xbmcgui.Dialog().select("Choose playback method for your themes", ["Direct Play", "Direct Stream"])
    if resp == 0:
        # Direct Play
        playback = "DirectPlay"
    elif resp == 1:
        # Direct Stream
        playback = "DirectStream"
    else:return

    # Set custom path for user
    tvtunes_path = xbmc.translatePath("special://profile/addon_data/script.tvtunes/").decode('utf-8')
    if xbmcvfs.exists(tvtunes_path):
        tvtunes = xbmcaddon.Addon(id="script.tvtunes")
        tvtunes.setSetting('custom_path_enable', "true")
        tvtunes.setSetting('custom_path', library)
        xbmc.log("TV Tunes custom path is enabled and set.")
    else:
        # if it does not exist this will not work so warn user, often they need to edit the settings first for it to be created.
        dialog = xbmcgui.Dialog()
        dialog.ok('Warning', 'The settings file for TV Tunes does not exist. Change a setting in TV Tunes, then come back and re-run.')
        xbmc.executebuiltin('Addon.OpenSettings(script.tvtunes)')
        return
        

    # Create library directory
    if not xbmcvfs.exists(library):
        xbmcvfs.mkdir(library)

    # Get every user view Id
    userViews = []
    url = "{server}/mediabrowser/Users/{UserId}/Items?format=json"
    result = doUtils.downloadUrl(url)
    
    for view in result[u'Items']:
        userviewId = view[u'Id']
        userViews.append(userviewId)


    # Get Ids with Theme Videos
    itemIds = {}
    for view in userViews:
        url = "{server}/mediabrowser/Users/{UserId}/Items?HasThemeVideo=True&ParentId=%s&format=json" % view
        result = doUtils.downloadUrl(url)
        if result[u'TotalRecordCount'] != 0:
            for item in result[u'Items']:
                itemId = item[u'Id']
                folderName = item[u'Name']
                folderName = utils.normalize_string(folderName.encode('utf-8'))
                itemIds[itemId] = folderName

    # Get paths for theme videos
    for itemId in itemIds:
        nfo_path = xbmc.translatePath("special://profile/addon_data/plugin.video.emby/library/%s/" % itemIds[itemId])
        # Create folders for each content
        if not xbmcvfs.exists(nfo_path):
            xbmcvfs.mkdir(nfo_path)
        # Where to put the nfos
        nfo_path = "%s%s" % (nfo_path, "tvtunes.nfo")

        url = "{server}/mediabrowser/Items/%s/ThemeVideos?format=json" % itemId
        result = doUtils.downloadUrl(url)

        # Create nfo and write themes to it
        nfo_file = open(nfo_path, 'w')
        pathstowrite = ""
        # May be more than one theme
        for theme in result[u'Items']:  
            if playback == "DirectPlay":
                playurl = playUtils.directPlay(theme)
            else:
                playurl = playUtils.directStream(result, server, theme[u'Id'], "ThemeVideo")
            pathstowrite += ('<file>%s</file>' % playurl.encode('utf-8'))
        
        # Check if the item has theme songs and add them   
        url = "{server}/mediabrowser/Items/%s/ThemeSongs?format=json" % itemId
        result = doUtils.downloadUrl(url)

        # May be more than one theme
        for theme in result[u'Items']:  
            if playback == "DirectPlay":
                playurl = playUtils.directPlay(theme)
            else:
                playurl = playUtils.directStream(result, server, theme[u'Id'], "Audio")
            pathstowrite += ('<file>%s</file>' % playurl.encode('utf-8'))

        nfo_file.write(
            '<tvtunes>%s</tvtunes>' % pathstowrite
        )
        # Close nfo file
        nfo_file.close()

    # Get Ids with Theme songs
    musicitemIds = {}
    for view in userViews:
        url = "{server}/mediabrowser/Users/{UserId}/Items?HasThemeSong=True&ParentId=%s&format=json" % view
        result = doUtils.downloadUrl(url)
        if result[u'TotalRecordCount'] != 0:
            for item in result[u'Items']:
                itemId = item[u'Id']
                folderName = item[u'Name']
                folderName = utils.normalize_string(folderName.encode('utf-8'))
                musicitemIds[itemId] = folderName

    # Get paths
    for itemId in musicitemIds:
        
        # if the item was already processed with video themes back out
        if itemId in itemIds:
            continue
        
        nfo_path = xbmc.translatePath("special://profile/addon_data/plugin.video.emby/library/%s/" % musicitemIds[itemId])
        # Create folders for each content
        if not xbmcvfs.exists(nfo_path):
            xbmcvfs.mkdir(nfo_path)
        # Where to put the nfos
        nfo_path = "%s%s" % (nfo_path, "tvtunes.nfo")
        
        url = "{server}/mediabrowser/Items/%s/ThemeSongs?format=json" % itemId
        result = doUtils.downloadUrl(url)

        # Create nfo and write themes to it
        nfo_file = open(nfo_path, 'w')
        pathstowrite = ""
        # May be more than one theme
        for theme in result[u'Items']:  
            if playback == "DirectPlay":
                playurl = playUtils.directPlay(theme)
            else:
                playurl = playUtils.directStream(result, server, theme[u'Id'], "Audio")
            pathstowrite += ('<file>%s</file>' % playurl.encode('utf-8'))

        nfo_file.write(
            '<tvtunes>%s</tvtunes>' % pathstowrite
        )
        # Close nfo file
        nfo_file.close()

def userPreferences():
    doUtils = DownloadUtils()
    addonSettings = xbmcaddon.Addon(id='plugin.video.emby')
    userPreferencesPage = UserPreferences("script-emby-kodi-UserPreferences.xml", addonSettings.getAddonInfo('path'), "default", "1080i")
    url = "{server}/mediabrowser/Users/{UserId}" 
    result = doUtils.downloadUrl(url)
    configuration = result[u'Configuration']
    userPreferencesPage.setConfiguration(configuration)
    userPreferencesPage.setName(result[u'Name'])
    userPreferencesPage.setImage(API().getUserArtwork(result,"Primary"))
    
    userPreferencesPage.doModal()
    if userPreferencesPage.isSave():
        url = "{server}/mediabrowser/Users/{UserId}/Configuration"
        postdata = userPreferencesPage.getConfiguration()
        doUtils.downloadUrl(url, postBody=postdata, type="POST")

##### BROWSE EMBY CHANNELS #####    
def BrowseChannels(id, folderid=None):
    
    _addon_id   =   int(sys.argv[1])
    _addon_url  =   sys.argv[0]
    
    xbmcplugin.setContent(int(sys.argv[1]), 'files')
    if folderid:
        url = "{server}/mediabrowser/Channels/" + id + "/Items?userid={UserId}&folderid=" + folderid + "&format=json"
    else:
        if id == "0": # id 0 is the root channels folder
            url = "{server}/mediabrowser/Channels?{UserId}&format=json"
        else:
            url = "{server}/mediabrowser/Channels/" + id + "/Items?userid={UserId}&format=json"

    results = DownloadUtils().downloadUrl(url)
    if results:
        result = results.get("Items")
        if(result == None):
            result = []

        item_count = len(result)
        current_item = 1;
            
        for item in result:
            id=str(item.get("Id")).encode('utf-8')
            type=item.get("Type").encode('utf-8')
            
            
            if(item.get("Name") != None):
                tempTitle = item.get("Name")
                tempTitle=tempTitle.encode('utf-8')
            else:
                tempTitle = "Missing Title"
                
            if type=="ChannelFolderItem":
                isFolder = True
            else:
                isFolder = False
            item_type = str(type).encode('utf-8')
            
            if(item.get("ChannelId") != None):
               channelId = str(item.get("ChannelId")).encode('utf-8')
            
            channelName = ''   
            if(item.get("ChannelName") != None):
               channelName = item.get("ChannelName").encode('utf-8')   
               
            if(item.get("PremiereDate") != None):
                premieredatelist = (item.get("PremiereDate")).split("T")
                premieredate = premieredatelist[0]
            else:
                premieredate = ""
            
            #mediaStreams=API().getMediaStreams(item, True)
                    
            #people = API().getPeople(item)
            
            # Process Genres
            genre = API().getGenre(item)
                    
            # Process UserData
            userData = item.get("UserData")
            PlaybackPositionTicks = '100'
            overlay = "0"
            favorite = "False"
            seekTime = 0
            if(userData != None):
                if userData.get("Played") != True:
                    overlay = "7"
                    watched = "true"
                else:
                    overlay = "6"
                    watched = "false"
                if userData.get("IsFavorite") == True:
                    overlay = "5"
                    favorite = "True"
                else:
                    favorite = "False"
                if userData.get("PlaybackPositionTicks") != None:
                    PlaybackPositionTicks = str(userData.get("PlaybackPositionTicks"))
                    reasonableTicks = int(userData.get("PlaybackPositionTicks")) / 1000
                    seekTime = reasonableTicks / 10000
            
            playCount = 0
            if(userData != None and userData.get("Played") == True):
                playCount = 1
            # Populate the details list
            details={'title'        : tempTitle,
                     'channelname'  : channelName,
                     'plot'         : item.get("Overview"),
                     'Overlay'      : overlay,
                     'playcount'    : str(playCount)}
            
            if item.get("Type") == "ChannelVideoItem":
                xbmcplugin.setContent(_addon_id, 'movies')
            elif item.get("Type") == "ChannelAudioItem":
                xbmcplugin.setContent(_addon_id, 'songs')

            # Populate the extraData list
            extraData={'thumb'        : API().getArtwork(item, "Primary")  ,
                       'fanart_image' : API().getArtwork(item, "Backdrop") ,
                       'poster'       : API().getArtwork(item, "poster") , 
                       'tvshow.poster': API().getArtwork(item, "tvshow.poster") ,
                       'banner'       : API().getArtwork(item, "Banner") ,
                       'clearlogo'    : API().getArtwork(item, "Logo") ,
                       'discart'      : API().getArtwork(item, "Disc") ,
                       'clearart'     : API().getArtwork(item, "Art") ,
                       'landscape'    : API().getArtwork(item, "Thumb") ,
                       'id'           : id ,
                       'rating'       : item.get("CommunityRating"),
                       'year'         : item.get("ProductionYear"),
                       'premieredate' : premieredate,
                       'genre'        : genre,
                       'playcount'    : str(playCount),
                       'itemtype'     : item_type}
                       
            if extraData['thumb'] == '':
                extraData['thumb'] = extraData['fanart_image']
                
            liz = xbmcgui.ListItem(tempTitle)

            artTypes=['poster', 'tvshow.poster', 'fanart_image', 'clearlogo', 'discart', 'banner', 'clearart', 'landscape', 'small_poster', 'tiny_poster', 'medium_poster','small_fanartimage', 'medium_fanartimage', 'medium_landscape', 'fanart_noindicators']
            
            for artType in artTypes:
                imagePath=str(extraData.get(artType,''))
                liz=PlaybackUtils().setArt(liz,artType, imagePath)
            
            liz.setThumbnailImage(API().getArtwork(item, "Primary"))
            liz.setIconImage('DefaultTVShows.png')
            #liz.setInfo( type="Video", infoLabels={ "Rating": item.get("CommunityRating") })
            #liz.setInfo( type="Video", infoLabels={ "Plot": item.get("Overview") })
            
            if type=="Channel":
                file = _addon_url + "?id=%s&mode=channels"%id
                xbmcplugin.addDirectoryItem(handle=_addon_id, url=file, listitem=liz, isFolder=True)
            
            elif isFolder == True:
                file = _addon_url + "?id=%s&mode=channelsfolder&folderid=%s" %(channelId, id)
                xbmcplugin.addDirectoryItem(handle=_addon_id, url=file, listitem=liz, isFolder=True)
            else:
                file = _addon_url + "?id=%s&mode=play"%id
                liz.setProperty('IsPlayable', 'true')
                xbmcplugin.addDirectoryItem(handle=_addon_id, url=file, listitem=liz)

    xbmcplugin.endOfDirectory(handle=int(sys.argv[1]))

##### GET NEXTUP EPISODES FOR TAGNAME #####    
def getNextUpEpisodes(tagname,limit):
    #if the addon is called with nextup parameter, we return the nextepisodes list of the given tagname
    xbmcplugin.setContent(int(sys.argv[1]), 'episodes')
    # First we get a list of all the in-progress TV shows - filtered by tag
    json_query_string = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "VideoLibrary.GetTVShows", "params": { "sort": { "order": "descending", "method": "lastplayed" }, "filter": {"and": [{"operator":"true", "field":"inprogress", "value":""}, {"operator": "contains", "field": "tag", "value": "%s"}]}, "properties": [ "title", "studio", "mpaa", "file", "art" ]  }, "id": "libTvShows"}' %tagname)
    
    json_result = json.loads(json_query_string)
    # If we found any, find the oldest unwatched show for each one.
    if json_result.has_key('result') and json_result['result'].has_key('tvshows'):
        for item in json_result['result']['tvshows']:
            addonSettings = xbmcaddon.Addon(id='plugin.video.emby')

            # If Ignore Specials is true only choose episodes from seasons greater than 0.
            if addonSettings.getSetting("ignoreSpecialsNextEpisodes")=="true":
                json_query2 = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "VideoLibrary.GetEpisodes", "params": { "tvshowid": %d, "sort": {"method":"episode"}, "filter": {"and": [ {"field": "playcount", "operator": "lessthan", "value":"1"}, {"field": "season", "operator": "greaterthan", "value": "0"} ]}, "properties": [ "title", "playcount", "season", "episode", "showtitle", "plot", "file", "rating", "resume", "tvshowid", "art", "streamdetails", "firstaired", "runtime", "writer", "cast", "dateadded", "lastplayed" ], "limits":{"end":1}}, "id": "1"}' %item['tvshowid'])
            else:
                json_query2 = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "VideoLibrary.GetEpisodes", "params": { "tvshowid": %d, "sort": {"method":"episode"}, "filter": {"field": "playcount", "operator": "lessthan", "value":"1"}, "properties": [ "title", "playcount", "season", "episode", "showtitle", "plot", "file", "rating", "resume", "tvshowid", "art", "streamdetails", "firstaired", "runtime", "writer", "cast", "dateadded", "lastplayed" ], "limits":{"end":1}}, "id": "1"}' %item['tvshowid'])

            if json_query2:
                json_query2 = json.loads(json_query2)
                if json_query2.has_key('result') and json_query2['result'].has_key('episodes'):
                    count = 0
                    for item in json_query2['result']['episodes']:
                        liz = createListItem(item)
                        xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=item['file'], listitem=liz)
                        count +=1
                        if count == limit:
                            break
    xbmcplugin.endOfDirectory(handle=int(sys.argv[1]))

def getInProgressEpisodes(tagname,limit):
    #if the addon is called with inprogressepisodes parameter, we return the inprogressepisodes list of the given tagname
    xbmcplugin.setContent(int(sys.argv[1]), 'episodes')
    # First we get a list of all the in-progress TV shows - filtered by tag
    json_query_string = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "VideoLibrary.GetTVShows", "params": { "sort": { "order": "descending", "method": "lastplayed" }, "filter": {"and": [{"operator":"true", "field":"inprogress", "value":""}, {"operator": "contains", "field": "tag", "value": "%s"}]}, "properties": [ "title", "studio", "mpaa", "file", "art" ]  }, "id": "libTvShows"}' %tagname)
    
    json_result = json.loads(json_query_string)
    # If we found any, find all in progress episodes for each one.
    if json_result.has_key('result') and json_result['result'].has_key('tvshows'):
        for item in json_result['result']['tvshows']:
            json_query2 = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "VideoLibrary.GetEpisodes", "params": { "tvshowid": %d, "sort": {"method":"episode"}, "filter": {"field": "inprogress", "operator": "true", "value":""}, "properties": [ "title", "playcount", "season", "episode", "showtitle", "plot", "file", "rating", "resume", "tvshowid", "art", "cast", "streamdetails", "firstaired", "runtime", "writer", "dateadded", "lastplayed" ]}, "id": "1"}' %item['tvshowid'])

            if json_query2:
                json_query2 = json.loads(json_query2)
                if json_query2.has_key('result') and json_query2['result'].has_key('episodes'):
                    count = 0
                    for item in json_query2['result']['episodes']:
                        liz = createListItem(item)
                        xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=item['file'], listitem=liz)
                        count +=1
                        if count == limit:
                            break
    xbmcplugin.endOfDirectory(handle=int(sys.argv[1]))

def getRecentEpisodes(tagname,limit):
    #if the addon is called with recentepisodes parameter, we return the recentepisodes list of the given tagname
    xbmcplugin.setContent(int(sys.argv[1]), 'episodes')
    # First we get a list of all the TV shows - filtered by tag
    json_query_string = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "VideoLibrary.GetTVShows", "params": { "sort": { "order": "descending", "method": "dateadded" }, "properties": [ "title","sorttitle" ], "filter": {"operator": "contains", "field": "tag", "value": "%s"} }, "id": "libTvShows"}' %tagname)    
    json_result = json.loads(json_query_string)
    
    # If we found any, put all tv show id's in a list
    if json_result.has_key('result') and json_result['result'].has_key('tvshows'):
        alltvshowIds = list()
        for tvshow in json_result['result']['tvshows']:
            alltvshowIds.append(tvshow["tvshowid"])
        alltvshowIds = set(alltvshowIds)
        
        #get all recently added episodes
        json_query2 = xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "VideoLibrary.GetEpisodes", "params": { "sort": {"order": "descending", "method": "dateadded"}, "filter": {"field": "playcount", "operator": "lessthan", "value":"1"}, "properties": [ "title", "playcount", "season", "episode", "showtitle", "plot", "file", "rating", "resume", "tvshowid", "art", "streamdetails", "firstaired", "runtime", "cast", "writer", "dateadded", "lastplayed" ]}, "limits":{"end":%d}, "id": "1"}' %limit)
        count = 0
        if json_query2:
            json_query2 = json.loads(json_query2)
            if json_query2.has_key('result') and json_query2['result'].has_key('episodes'):
                for item in json_query2['result']['episodes']:
                    if item["tvshowid"] in alltvshowIds:
                        liz = createListItem(item)
                        xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=item['file'], listitem=liz)
                        count += 1
                    if count >= limit:
                        break
    xbmcplugin.endOfDirectory(handle=int(sys.argv[1]))
    
def createListItem(item):
       
    liz = xbmcgui.ListItem(item['title'])
    liz.setInfo( type="Video", infoLabels={ "Title": item['title'] })
    liz.setProperty('IsPlayable', 'true')
    liz.setInfo( type="Video", infoLabels={ "duration": str(item['runtime']/60) })
    
    if "episode" in item:
        episode = "%.2d" % float(item['episode'])
        liz.setInfo( type="Video", infoLabels={ "Episode": item['episode'] })
    
    if "season" in item:
        season = "%.2d" % float(item['season'])
        liz.setInfo( type="Video", infoLabels={ "Season": item['season'] })
        
    if season and episode:
        episodeno = "s%se%s" %(season,episode)
        liz.setProperty("episodeno", episodeno)
        
    if "firstaired" in item:
        liz.setInfo( type="Video", infoLabels={ "Premiered": item['firstaired'] })
    
    plot = item['plot']
    liz.setInfo( type="Video", infoLabels={ "Plot": plot })
    
    if "showtitle" in item:
        liz.setInfo( type="Video", infoLabels={ "TVshowTitle": item['showtitle'] })
    
    if "rating" in item:
        liz.setInfo( type="Video", infoLabels={ "Rating": str(round(float(item['rating']),1)) })
    liz.setInfo( type="Video", infoLabels={ "Playcount": item['playcount'] })
    if "director" in item:
        liz.setInfo( type="Video", infoLabels={ "Director": " / ".join(item['director']) })
    if "writer" in item:
        liz.setInfo( type="Video", infoLabels={ "Writer": " / ".join(item['writer']) })
        
    if "cast" in item:
        listCast = []
        listCastAndRole = []
        for castmember in item["cast"]:
            listCast.append( castmember["name"] )
            listCastAndRole.append( (castmember["name"], castmember["role"]) ) 
        cast = [listCast, listCastAndRole]
        liz.setInfo( type="Video", infoLabels={ "Cast": cast[0] })
        liz.setInfo( type="Video", infoLabels={ "CastAndRole": cast[1] })
    
    liz.setProperty("resumetime", str(item['resume']['position']))
    liz.setProperty("totaltime", str(item['resume']['total']))
    liz.setArt(item['art'])
    liz.setThumbnailImage(item['art'].get('thumb',''))
    liz.setIconImage('DefaultTVShows.png')
    liz.setProperty("dbid", str(item['episodeid']))
    liz.setProperty("fanart_image", item['art'].get('tvshow.fanart',''))
    for key, value in item['streamdetails'].iteritems():
        for stream in value:
            liz.addStreamInfo( key, stream )
    
    return liz
    
##### GET EXTRAFANART FOR LISTITEM #####
def getExtraFanArt():
    itemPath = ""
    embyId = ""
    #get extrafanart for listitem - this will only be used for skins that actually call the listitem's path + fanart dir... 
    try:
        #only do this if the listitem has actually changed
        itemPath = xbmc.getInfoLabel("ListItem.FileNameAndPath")
            
        if not itemPath:
            itemPath = xbmc.getInfoLabel("ListItem.Path")
        
        if ("/tvshows/" in itemPath or "/musicvideos/" in itemPath or "/movies/" in itemPath):
            embyId = itemPath.split("/")[-2]

            #we need to store the images locally for this to work because of the caching system in xbmc
            fanartDir = xbmc.translatePath("special://thumbnails/emby/" + embyId + "/")
            
            if not xbmcvfs.exists(fanartDir):
                #download the images to the cache directory
                xbmcvfs.mkdir(fanartDir)
                item = ReadEmbyDB().getFullItem(embyId)
                if item != None:
                    if item.has_key("BackdropImageTags"):
                        if(len(item["BackdropImageTags"]) > 0):
                            totalbackdrops = len(item["BackdropImageTags"]) 
                            for index in range(0,totalbackdrops): 
                                backgroundUrl = API().getArtwork(item, "Backdrop",str(index))
                                fanartFile = os.path.join(fanartDir,"fanart" + str(index) + ".jpg")
                                li = xbmcgui.ListItem(str(index), path=fanartFile)
                                xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=fanartFile, listitem=li)
                                xbmcvfs.copy(backgroundUrl,fanartFile) 
                
            else:
                #use existing cached images
                dirs, files = xbmcvfs.listdir(fanartDir)
                count = 1
                for file in files:
                    count +=1
                    li = xbmcgui.ListItem(file, path=os.path.join(fanartDir,file))
                    xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=os.path.join(fanartDir,file), listitem=li)
    except:
        pass
    
    #always do endofdirectory to prevent errors in the logs
    xbmcplugin.endOfDirectory(int(sys.argv[1]))


def addDirectoryItem(label, path, folder=True):
    li = xbmcgui.ListItem(label, path=path)
    li.setThumbnailImage("special://home/addons/plugin.video.emby/icon.png")
    li.setArt({"fanart":"special://home/addons/plugin.video.emby/fanart.jpg"})
    li.setArt({"landscape":"special://home/addons/plugin.video.emby/fanart.jpg"})
    xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=path, listitem=li, isFolder=folder)    
    
# if the addon is called without parameters we show the listing...    
def doMainListing():
    
    xbmcplugin.setContent(int(sys.argv[1]), 'files')    
    #get emby nodes from the window props
    embyProperty = WINDOW.getProperty("Emby.nodes.total")
    if embyProperty:
        totalNodes = int(embyProperty)
        for i in range(totalNodes):
            path = WINDOW.getProperty("Emby.nodes.%s.index" %str(i))
            if not path:
                path = WINDOW.getProperty("Emby.nodes.%s.content" %str(i))
            label = WINDOW.getProperty("Emby.nodes.%s.title" %str(i))
            if path:
                addDirectoryItem(label, path)
    
    # some extra entries for settings and stuff. TODO --> localize the labels
    addDirectoryItem("Settings", "plugin://plugin.video.emby/?mode=settings")
    addDirectoryItem("Perform manual sync", "plugin://plugin.video.emby/?mode=manualsync")
    addDirectoryItem("Add user to session", "plugin://plugin.video.emby/?mode=adduser")
    addDirectoryItem("Configure user preferences", "plugin://plugin.video.emby/?mode=userprefs")
    addDirectoryItem("Perform local database reset (full resync)", "plugin://plugin.video.emby/?mode=reset")
    addDirectoryItem("Cache all images to Kodi texture cache (advanced)", "plugin://plugin.video.emby/?mode=texturecache")
    addDirectoryItem("Sync Emby Theme Media to Kodi", "plugin://plugin.video.emby/?mode=thememedia")
    
    xbmcplugin.endOfDirectory(int(sys.argv[1]))                
