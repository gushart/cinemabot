"""
Телеграмм бот с возможностью поиска фильма по нескольким сайтам.
"""
import os
import aiohttp
from aiogram import Bot, types
from aiogram.dispatcher import Dispatcher
from aiogram.utils import executor
from bs4 import BeautifulSoup

HEADERS = {'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) '
                         'AppleWebKit/537.36 (KHTML, like Gecko)'
                         'Chrome/77.0.3865.121 '
                         'Safari/537.36'}

with open('api_key_tmdb.txt', 'r', ) as key:
    TMDB_API_KEY = key.read().strip()

PROXY_HOST = os.environ.get('PROXY', None)
PROXY_CREDENTIALS = os.environ.get('PROXY_CREDS', None)
if PROXY_CREDENTIALS:
    LOGIN, PASSWORD = PROXY_CREDENTIALS.split(':')
    PROXY_AUTH = aiohttp.BasicAuth(login=LOGIN, password=PASSWORD)
else:
    PROXY_AUTH = None

BOT = Bot(token=os.environ['BOT_TOKEN'],
          proxy=PROXY_HOST, proxy_auth=PROXY_AUTH)

DP = Dispatcher(BOT)


async def fetch_movie_link(session, movie_name, source):
    """
    Возвращает прямую ссылку на описание фильма, в случае если источником выбран
    Кинопоиск или IMDB.
    Если фильм не найден - None
    """
    params = {'url': 'https://www.imdb.com/find', 'request': {'s': 'tt', 'q': movie_name},
              'source': 'https://www.imdb.com',
              'first_tag': 'tr', 'first_class': 'findResult odd',
              'second_tag': 'a', 'second_class': 'href',
              }

    if source == 'kp':
        movie_name = movie_name.replace(' ', '+')
        params['url'] = 'https://www.kinopoisk.ru/level=7&m_act[what]=content&m_act[find]=' + \
                        movie_name
        params['first_tag'] = 'div'
        params['first_class'] = 'info'
        params['request'] = {}
        params['source'] = 'https://www.kinopoisk.ru'

    async with session.get(params['url'], headers=HEADERS, params=params['request']) as resp:
        print(resp.status)
        resp_text = await resp.text()
        soup = BeautifulSoup(resp_text)
        first_search = soup.find(params['first_tag'], attrs={'class': params['first_class']})
        if not first_search:
            return None
        second_search = first_search.find(params['second_tag']).get(params['second_class'])
        return params['source'] + second_search


async def fetch_movie_info_imdb(session, movie_link):
    """
    Возвращаем информацию о фильме, если источником выбран imdb.
    Возвращаемый объект - список.
    Состоит из самого близкого найденного названия названия фильма,
    ссылки на постер, и описание фильма.
    В случае отсутствия описания или/и постера возвращаются строки No Poster/Description
    """
    params = [{'first_tag': 'div', 'first_class': 'title_block',
               'second_tag': 'a', 'second_class': 'title',
               'type': 'get_name'},
              {'first_tag': 'div', 'first_class': 'poster',
               'second_tag': 'img', 'second_class': 'src',
               'type': 'get_info'}]
    result = []
    async with session.get(movie_link, headers=HEADERS) as resp:
        print(resp.status)
        resp_text = await resp.text()
        soup = BeautifulSoup(resp_text)
        for param in params:
            first_search = soup.find(param['first_tag'], attrs={'class': param['first_class']})
            if not first_search and param['type'] == 'get_info':
                result.append('No Poster')
            else:
                second_search = first_search.find(param['second_tag']).get(param['second_class'])

                if param['type'] == 'get_name':
                    self = first_search.find('h1').text
                    if second_search:
                        result.append(second_search + ' ' + self)
                    else:
                        result.append(self)

                    continue
                if param['type'] == 'get_info':
                    result.append(second_search)

            movie_descr = soup.find('div', attrs={'class': 'summary_text'})
            if movie_descr.find('a'):
                result.append('No description')
            else:
                result.append(movie_descr.text)  # "Add a Plot »" - if no descr.

    return result


async def fetch_movie_info_kp(session, movie_link):
    """
       Возвращаем информацию о фильме, если источником выбран imdb.
       Возвращаемый объект - список.
       Состоит из самого близкого найденного названия названия фильма,
       ссылки на постер, и описание фильма.
       В случае отсутствия описания - No description
       В случае бана - возращаем строку о том, что нас забанили
       """
    async with session.get(movie_link, headers=HEADERS) as resp:
        print(resp.status)
        resp_text = await resp.text()
        soup = BeautifulSoup(resp_text)
        try:
            movie_name = soup.find('h1', attrs={'class': 'moviename-big'}).text
        except AttributeError:
            return ['Banned by kp', '', '']
        poster_link = soup.find('div', attrs={'class': 'movie-info__sidebar'})
        poster_link = poster_link.find('img').get('src')
        try:
            movie_descr = soup.find('div', attrs={'class': 'brand_words film-synopsys'}).text
            movie_descr = movie_descr.replace('\xa0', ' ').replace('\x85', ' ')
        except AttributeError:
            movie_descr = 'No description'

        return [movie_name, poster_link, movie_descr]


async def fetch_movie_tmdb(session, movie_name):
    """
    Возвращаем название фильма, информацию о фильме и ссылку на постер.
    В информации включены оценка и описание.
    None - если фильм/сериал не был найден.
    """

    request_params = {'query': movie_name, 'api_key': TMDB_API_KEY, 'language': 'ru-RU'}
    search_url = 'https://api.themoviedb.org/3/search/'

    for watch_type in ['movie', 'tv']:
        async with session.get(search_url + watch_type,
                               headers=HEADERS, params=request_params) as resp:
            print(resp.status)
            resp = await resp.json()
            if resp['total_results'] == 0:
                continue
        movie = resp['results'][0]
        movie_info = movie['title'] + ':\n' + 'Оценка: ' + \
                     str(movie['vote_average']) + ' (10)' + '\n'

        if movie['overview']:
            movie_info += 'Сюжет: ' + movie['overview']
        if movie['poster_path']:
            poster_url = 'https://image.tmdb.org/t/p/w500' + movie['poster_path']
        elif movie['backdrop_path']:
            poster_url = 'https://image.tmdb.org/t/p/w500' + movie['backdrop_path']
        else:
            poster_url = None
        return movie['title'], movie_info, poster_url

    return None, None, None


async def fetch_online_watch(session, movie_name):
    """
    Возвращаем ccылку на просмотр фильма из гугла.
    """
    query = 'Смотреть онлайн ' + movie_name
    async with session.get('https://www.google.ru/search',
                           headers=HEADERS, params={'q': query}) as resp:
        resp_text = await resp.text()
        soup = BeautifulSoup(resp_text)
        return soup.find('div', attrs={'class' : 'r'}).find('a').get('href')


@DP.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    await message.answer("Hi!\nI'm CinemaBot!\nPowered by aiogram.")


@DP.message_handler(commands=['help'])
async def send_help(message: types.Message):
    await message.answer('Write film/TV serial name to find any information about it. '
                         'You can also try:\n' + \
                         '#kp *film name* - to use kinopoisk information '
                         '\n#im *filmname* - to use imdb')


@DP.message_handler()
async def echo(message: types.Message):
    """
    Основные вызовы бота.
    """
    async with aiohttp.ClientSession() as session:
        if message.text[:1] == '#':  # Блок, если выбран иной источник
            other_source_type = message.text[1:3]
            if other_source_type in ['im', 'kp']:
                movie_link = await fetch_movie_link(session, message.text[4:],
                                                    source=other_source_type)
                if not movie_link:
                    await message.answer('Please write the correct Film '
                                         'or TV show name or change source')
                else:
                    if other_source_type == 'im':
                        movie_info = await fetch_movie_info_imdb(session, movie_link)
                    else:
                        movie_info = await fetch_movie_info_kp(session, movie_link)

                    await message.answer(movie_info[0].strip() + ':\n' +
                                         movie_info[2].strip() + '\n')

                    watch_link = await fetch_online_watch(session, movie_info[0].strip())
                    await message.answer('Watch it online:\n' + watch_link)

                    await message.answer_photo(movie_info[1])

            else:
                await message.answer('Please write the correct Film or TV show name')
        else:
            movie_name, movie_info, poster_url = await fetch_movie_tmdb(session, message.text)
            if not movie_info:
                await message.answer('Please write the correct Film or TV show name')

            else:
                await message.answer(movie_info)
                watch_link = await fetch_online_watch(session, movie_name)
                await message.answer('Watch it online:\n' + watch_link)

                if poster_url:
                    await message.answer_photo(poster_url)


if __name__ == '__main__':
    executor.start_polling(DP)
