# -*- coding: utf-8 -*-
import requests
import json
import datetime
import logging
from logging.config import dictConfig
import tablib
from ig_app import celery

logging_config = dict(version=1, formatters={'f': {'format': '%(asctime)s %(name)-12s %(levelname)-8s %(message)s'}},
                      handlers={'h': {'class': 'logging.StreamHandler', 'formatter': 'f', 'level': logging.DEBUG}},
                      loggers={'root': {'handlers': ['h'], 'level': logging.DEBUG},
                               'foursquare': {'handlers': ['h'], 'level': logging.DEBUG},
                               'instagram': {'handlers': ['h'], 'level': logging.DEBUG}, })
dictConfig(logging_config)
fq_logger = logging.getLogger('foursquare')
ig_logger = logging.getLogger('instagram')


def instagram(path, **kwargs):
    params = {'access_token': '15722.2979bff.125403efd1564266a12927d3f5e2cb94'}
    params.update(**kwargs)
    url = 'https://api.instagram.com/v1/'
    response = requests.get(url + path, params=params)
    resp_json = json.loads(response.text)
    if not response.status_code == requests.codes.ok:
        return "Instagram Error: {}".format(resp_json['meta'])
    else:
        return resp_json['data']


def foursquare_location(query):
    params = {'client_id': '1ED25XBF350S5HMUTXLCDUTB4PDXPEVQH43O3EFYXDFD2W3G',
              'client_secret': '0ILK2DDHYE3T2XZWV1FCHNKI10UESFD2STGV3OCISOXTGNNQ',
              'v': '20130815'}
    params.update({'query': query, 'intent': 'global'})
    response = requests.get('https://api.foursquare.com/v2/venues/search',
                            params=params)
    resp_json = json.loads(response.text)
    if not response.status_code == requests.codes.ok:
        return "Foursquare Error: {}".format(resp_json['meta'])
    else:
        fq_logger.debug(resp_json['response']['venues'][0])
        return resp_json['response']['venues'][0]  # return first result


def instagram_recent_media(location_id, date_range=1, limit=100):
    """
    date_range: num of days, all media returned will be taken
    in last {date_range} days
    """
    min_date = datetime.datetime.utcnow() - datetime.timedelta(days=date_range)
    min_timestamp = min_date.strftime("%s")
    path = 'locations/{}/media/recent/'.format(location_id)
    sub_media = instagram(path, count=limit, min_timestamp=min_timestamp)
    media = sub_media
    while len(media) != limit:
        if len(sub_media) == 0 or 'Error' in sub_media:
            break
        min_id = sub_media[-1]['id']
        count = limit - len(media)
        sub_media = instagram(path, min_timestamp=min_timestamp, max_id=min_id, count=count)
        media += sub_media
    ig_logger.debug('Recent media count: {}'.format(len(media)))
    return media


def user_last_media(user_id, limit=100):
    """
    user_id: instagram user_id
    limit: count of last user media
    """
    user_info = instagram('users/{}/'.format(user_id))
    path = 'users/{}/media/recent/'.format(user_id)
    sub_media = instagram(path, count=limit)
    user_media = sub_media

    while len(user_media) != limit:
        if len(sub_media) == 0 or 'Error' in sub_media:
            break
        max_id = sub_media[0]['id']
        count = limit - len(user_media)
        sub_media = instagram(path, max_id=max_id, count=count)
        user_media += sub_media
    return user_info, user_media


@celery.task(bind=True)
def job(self, hotel, recent_media_limit=100, recent_media_drange=1, user_media_limit=100):
    progress = 0
    book_title = '{}_{}'.format(hotel, datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'))
    users_sheet = tablib.Dataset(headers=['Id', 'Username', 'Full name', 'Follows', 'Followed_by'], title='User Info')
    media_sheet = tablib.Dataset(headers=['Username', 'PostID', 'Caption', 'Users in photo', 'Year',
                                          'Month', 'Day', '# of likes', '# of comments', 'photo/video',
                                          'Lat (loc)', 'Long (loc)', 'Name (loc)'], title='Last media')
    try:
        fq_location = foursquare_location(hotel)['id']
        ig_location = instagram('locations/search', foursquare_v2_id=fq_location)[0]['id']
    except Exception as err:
        error = 'Location search: {}'.format(err)
        self.update_state(state='ERORR', meta={'current': progress, 'total': 100, 'status': error})
        return {'current': 100, 'total': 100, 'status': error, 'result': 'error'}
    else:
        progress += 10
        self.update_state(state='PROGRESS', meta={'current': progress, 'total': 100, 'status': 'foursquare location'})
        location_media = instagram_recent_media(ig_location, date_range=recent_media_drange, limit=recent_media_limit)
        if not location_media:
            error = 'Error: No media for "{}" in last {} days'.format(hotel, recent_media_drange)
            self.update_state(state='ERORR', meta={'current': progress, 'total': 100, 'status': error})
            return {'current': 100, 'total': 100, 'status': error, 'result': 'error'}
        else:
            users = set([media['user']['id'] for media in location_media])
            progress += 10
            self.update_state(state='PROGRESS', meta={'current': progress, 'total': 100, 'status': 'recent media'})
            for user_id in users:
                progress += 70 / len(users)
                info, media = user_last_media(user_id)
                self.update_state(state='PROGRESS', meta={'current': progress, 'total': 100, 'status': 'crawl user {}'.format(user_id)})
                users_sheet.append((info['id'], info['username'], info['full_name'], info['counts']['follows'], info['counts']['followed_by']))
                for post in media:
                    users_in_photo = len(post['users_in_photo']) if post['users_in_photo'] else None
                    year, month, day = datetime.datetime.fromtimestamp(int(post['created_time'])).strftime('%Y-%m-%d').split('-')
                    caption = post['caption'].get('text') if post.get('caption') else None
                    latitude, longitude, name = (post['location'].get('latitude'), post['location'].get('longitude'), post['location'].get('name')) if post.get('location') else (None, None, None)
                    media_sheet.append((post['user']['username'], post['id'], caption, users_in_photo, year, month, day,
                                        post['likes']['count'], post['comments']['count'], post['type'], latitude, longitude, name))
                ig_logger.debug('user_id: {}, media count: {}'.format(user_id, len(media)))
            book = tablib.Databook((users_sheet, media_sheet))
            self.update_state(state='PROGRESS', meta={'current': 90, 'total': 100, 'status': 'write to file'})
            with open('ig_app/static/xls/{}.xls'.format(book_title), 'wb') as f:
                f.write(book.xls)
            return {'current': 100, 'total': 100, 'status': 'Task completed!', 'result': 42}

if __name__ == '__main__':
    hotel = 'LA Four Seasons Los Angeles'
    airport = 'Los Angeles International Airport'
    job(hotel)
    # job(airport)
