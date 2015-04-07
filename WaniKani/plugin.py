###
# Copyright (c) 2014, Acalewin
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions, and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions, and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#   * Neither the name of the author of this software nor the name of
#     contributors to this software may be used to endorse or promote products
#     derived from this software without specific prior written consent.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

###

import json
import requests
import datetime

import supybot.utils as utils
import supybot.dbi as dbi
from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks
try:
    from supybot.i18n import PluginInternationalization
    _ = PluginInternationalization('WaniKani')
except ImportError:
    # Placeholder that allows to run the plugin on a bot
    # without the i18n module
    _ = lambda x: x


class WKUser(dbi.Record):
    __fields__ = [
        ('nick', eval),
        ('apikey', eval),
    ]


class WKUserDB(plugins.DbiChannelDB):
    class DB(dbi.DB):
        Record = WKUser

        def add(self, nick, apikey):
            record = self.Record(nick=nick, apikey=apikey)
#            while self.remove(nick): pass
            super(self.__class__, self).add(record)

        def remove(self, nick):
            size = self.size()
            for i in range(1, size+1):
                try:
                    u = self.get(i)
                    if u.nick == nick:
                        super(self.__class__, self).remove(i)
                        return True
                except: #Bad form, I know. I need to track down where NoRecordError comes from
                    pass
            return False

        def getapikey(self, nick):
            size = self.size()
            for i in range(1, size+1):
                try:
                    u = self.get(i)
                    if u.nick == nick:
                        return u.apikey
                except: #Yeah, yeah.... :(
                    pass
            return ''


WKUSERDB = plugins.DB('WaniKani', {'flat': WKUserDB})


class WaniKani(callbacks.Plugin):
    """Add the help for "@plugin help WaniKani" here
    This should describe *how* to use this plugin."""
    threaded = True

    def __init__(self, irc):
        self.__parent = super(WaniKani, self)
        self.__parent.__init__(irc)
        self.db = WKUSERDB()

    def wkadd(self, irc, msg, args, apikey):
        """<apikey>
        Links the API key to the caller's nickname"""
        nick = msg.nick
        channel = msg.args[0]
        if apikey:
            irc.reply('Storing WK API Key %s for user %s' % (apikey, nick))
        else:
            irc.reply('No API Key reported')
        #while self.db.remove(nick): pass
        self.db.add('#wanikani', nick, apikey)
    add = wrap(wkadd, ['anything'])

    def WK_getstats(self, apikey, target='total'):
        url = "https://www.wanikani.com/api/user/%s/%s/" % (apikey, 'srs-distribution')
        data = ''
        resp_str = ''
        if not target in ('kanji', 'vocabulary', 'total', 'radicals'):
            return 'Unknown parameter passed in'
        try:
            resp = requests.get(url=url)
            data = json.loads(resp.content)
            lvl = data['user_information']['level']
            data = data.get('requested_information')
            resp_str = 'LVL: %d - appr: %d - guru: %d - mast: %d - en: %d - brnd: %d' % (lvl, data['apprentice'][target],
                                                                               data['guru'][target],
                                                                               data['master'][target],
                                                                               data['enlighten'][target],
                                                                               data['burned'][target])
        except:
            resp_str = "Error loading data from WK. Yell at someone."
        return resp_str

    def WK_getkanjistats(self, apikey):
        return self.WK_getstats(apikey, 'kanji')

    def WK_getvocabstats(self, apikey):
        return self.WK_getstats(apikey, 'vocabulary')

    def WK_getradicalstats(self, apikey):
        return self.WK_getstats(apikey, 'radicals')

    def WK_getallstats(self, apikey):
        return self.WK_getstats(apikey, 'total')

    def WK_getreviews(self, apikey):
        if not apikey:
            return 'No key found. Link it with the "add" command.'
        url = "https://www.wanikani.com/api/user/%s/%s/" % (apikey, 'study-queue')
        resp = ''
        try:
            resp = requests.get(url=url)
            resp.raise_for_status()
            data = json.loads(resp.content)
            data = data.get('requested_information')
            reviews = data.get('reviews_available', 0)
            nextreview = 'NOW'
            if (reviews == 0):
                nextreview = 'VACATION' if not data['next_review_date'] else \
                             datetime.datetime.fromtimestamp(data['next_review_date'])
                if (nextreview != 'VACATION'):
                    nextreview = nextreview - datetime.datetime.now()
                    nextreview = datetime.timedelta(days=nextreview.days,
                                                    seconds=round(nextreview.seconds/60.0))
        except requests.exceptions.ConnectionError:
            return 'Error loading data from WK. Connection Error.'
        except requests.exceptions.HTTPError as e:
            return 'HTTP Error. Got back %s' % e.response.status_code
        except AttributeError as e:
            return 'I think your key is wrong. I could not get review data'
            
        return 'L: %d - R: %d - NEXT: %s - HR: %d - DAY: %d' % (data['lessons_available'] or 0, reviews,
                                                                nextreview, data.get('reviews_available_next_hour') or 0,
                                                                data['reviews_available_next_day'] or 0)

    def itemstats(self, irc, msg, args, subset):
        """ [<kanji|radicals|vocab>]
        Returns the item statistics all items or the indicated subset"""

        channel = msg.args[0]
        user = msg.nick
        if (channel not in ('#wanikani', 'cirno-tan')):
            irc.reply('This command can only be used in #wanikani or via PM')
            return
        apikey = self.db.getapikey(channel, user) or self.db.getapikey('cirno-tan', user)

        if not apikey:
            irc.reply('No API key found for %s. use the add command to set it.' % user)
            return
        if not subset:
            irc.reply(self.WK_getallstats(apikey))
        elif subset.lower() == 'kanji':
            irc.reply(self.WK_getkanjistats(apikey))
        elif subset.lower() == 'vocab':
            irc.reply(self.WK_getvocabstats(apikey))
        elif subset.lower() == 'radicals':
            irc.reply(self.WK_getradicalstats(apikey))
        else:
            irc.reply("you provided a stupid option, but you can try https://www.wanikani.com/community/people/%s" % subset)
    itemstats = wrap(itemstats, [optional('anything')])

    def reviews(self, irc, msg, args):
        """ No inputs
        Returns the user's current review count, or time to next review. Use the 'add' command from the WaniKani plugin to link your apikey."""
        channel = msg.args[0]
        if (channel not in ('#wanikani', 'cirno-tan')):
            irc.reply("This command can only be used in #wanikani or via PM")
            return
        user = msg.nick
        apikey = self.db.getapikey('#wanikani', user) or self.db.getapikey('cirno-tan', user)
        irc.reply(self.WK_getreviews(apikey))
    reviews = wrap(reviews)

Class = WaniKani


# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79:
