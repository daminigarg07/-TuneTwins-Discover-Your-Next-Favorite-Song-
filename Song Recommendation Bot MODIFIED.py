import logging
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, ConversationHandler, CallbackContext
import pandas as pd
import spotipy.util as util
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from sklearn.metrics.pairwise import cosine_similarity
import warnings
warnings.filterwarnings('ignore')

# Spotify API credentials
client_id = 'CLIENT ID'
client_secret = 'CLIENT SECRET'
username = 'USERNAME'
scope = 'SCOPE'
redirect_uri = 'REDIRECT URL'

# Authenticate and initialize Spotify client
# Uncomment below to authenticate via user token if needed
# token = util.prompt_for_user_token(username=username,
#                                   scope=scope,
#                                   client_id=client_id,
#                                   client_secret=client_secret,
#                                   redirect_uri=redirect_uri)

sp = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(client_id=client_id, client_secret=client_secret))

# Define conversation states for the bot
START, DISCOVER_ARTIST, RANDOM_SONG_REC, ARTIST, SONG, TOP = range(6)

# Start conversation and provide available options
def start(update, context):
    context.user_data.clear()
    user = update.message.from_user
    update.message.reply_text(f"Hello, {user.first_name}! I'm your music discovery bot. How can I assist you today?")
    update.message.reply_text("To discover an artist based on a song, type /discover_artist")
    update.message.reply_text("For song recommendations, type /songrec")
    update.message.reply_text("To get the top 10 tracks of your favorite artist, type /top10")
    update.message.reply_text("To cancel the conversation, type /cancel")
    return START

# Prompt the user to discover an artist
def discover_artist(update, context):
    update.message.reply_text("Please enter the artist's name you'd like to discover:")
    text = update.message.text
    if text == '/start':
        return START
    else:
        return DISCOVER_ARTIST

# Process artist input from user and prompt for a song
def discover_artist_input(update, context):
    text = update.message.text
    if text == '/start':
        return START
    else:
        artist = update.message.text
        context.user_data['artist'] = artist
        update.message.reply_text("Great! Now, enter a song you like:")
        return RANDOM_SONG_REC

# Recommend songs based on artist and song input
def song_rec(update, context):
    song = update.message.text
    artist = context.user_data['artist']

    # Get song recommendations using helper functions
    recommendation_df = get_data(artist)
    recommendation = rec(song, recommendation_df)
    if not recommendation:
        update.message.reply_text("No recommendations found for the provided artist and song.")
    else:
        update.message.reply_text("Here are some song recommendations for you:")
        for idx, rec_song in enumerate(recommendation, start=1):
            update.message.reply_text(f"{idx}. {rec_song}")
    
    # Display available commands after showing recommendations
    update.message.reply_text("To discover an artist, type /discover_artist")
    update.message.reply_text("For song recommendations, type /songrec")
    update.message.reply_text("To get top 10 tracks, type /top10")
    update.message.reply_text("To cancel, type /cancel")

    return START

# Prompt for random song recommendations
def random_song_rec(update, context):
    context.user_data.clear()  # Clear previous user data
    update.message.reply_text("Let's find some random song recommendations. Enter the artist name you like:")
    return ARTIST

# Process the artist input and ask for a song
def artist_input(update, context):
    artist = update.message.text
    context.user_data['artist'] = artist
    update.message.reply_text("Great! Now, enter a song you like:")
    return SONG

# Recommend random songs based on artist and song input
def random_song_rec_input(update, context):
    song = update.message.text
    artist = context.user_data['artist']

    # Get random song recommendations using helper functions
    recommendation_df = get_data(artist)
    recommendations = rec_all(artist, recommendation_df, song)
    if not recommendations:
        update.message.reply_text("No recommendations found for the provided artist and song.")
    else:
        update.message.reply_text("Here are some random song recommendations:")
        for idx, rec_songs in enumerate(recommendations, start=1):
            update.message.reply_text(f"{idx}. {rec_songs}")

    # Display available commands after showing recommendations
    update.message.reply_text("To discover an artist, type /discover_artist")
    update.message.reply_text("For song recommendations, type /songrec")
    update.message.reply_text("To get top 10 tracks, type /top10")
    update.message.reply_text("To cancel, type /cancel")

    return START

# Prompt for top 10 tracks of an artist
def top_10_rec(update, context):
    context.user_data.clear()  # Clear previous user data
    update.message.reply_text("Enter the artist's name to get their top 10 tracks:")
    return TOP

# Retrieve and display top 10 tracks of the artist
def top_10(update, context):
    artist = update.message.text

    top10rec = top10(artist)
    if not top10rec:
        update.message.reply_text("No top tracks found for the provided artist.")
    else:
        update.message.reply_text("Here are the top 10 tracks:")
        for idx, rec_songs in enumerate(top10rec, start=1):
            update.message.reply_text(f"{idx}. {rec_songs}")

    # Display available commands after showing top 10 tracks
    update.message.reply_text("To discover an artist, type /discover_artist")
    update.message.reply_text("For song recommendations, type /songrec")
    update.message.reply_text("To get top 10 tracks, type /top10")
    update.message.reply_text("To cancel, type /cancel")
    
    return START

# Display available commands when user types /help
def help_command(update: Update, context: CallbackContext) -> None:
    help_text = "Here are the available commands:\n"
    help_text += "/start - Start a new conversation\n"
    help_text += "/discover_artist - Discover an artist based on their song\n"
    help_text += "/songrec - Get song recommendations\n"
    help_text += "/top10 - Get top 10 tracks of an artist\n"
    help_text += "/cancel - Cancel the current conversation\n"
    update.message.reply_text(help_text)

# Cancel the conversation
def cancel(update, context):
    update.message.reply_text("You have canceled the conversation.")
    update.message.reply_text("To discover an artist, type /discover_artist")
    update.message.reply_text("For song recommendations, type /songrec")
    update.message.reply_text("To get top 10 tracks, type /top10")
    return START

# Fetch artist and track data from Spotify
def get_data(artist):
    artist_info = sp.search(artist, limit=1, offset=0, type='artist', market=None)
    if not artist_info or not artist_info['artists']['items']:
        print("Artist not found.")
        return

    artist_info = artist_info['artists']['items'][0]
    artist_id = artist_info['id']

    # Get albums by the artist
    albums = sp.artist_albums(artist_id, album_type=["album", "single", "appears_on"], limit=50)
    albums_df = pd.DataFrame(albums['items'])
    tracks_df = pd.DataFrame()

    # Retrieve tracks from each album
    if not albums_df.empty:
        for album_id in albums_df['id']:
            album_tracks = sp.album_tracks(album_id, limit=50, offset=0, market=None)
            tracks_df = pd.concat([tracks_df, pd.DataFrame(album_tracks['items'])])
    else:
        print("No albums found for the artist.")
        return
    tracks_df = tracks_df.reset_index(drop=True)

    # Get audio features for the tracks
    track_ids = tracks_df['id']
    chunk_size = 50
    chunks = [track_ids[i:i + chunk_size] for i in range(0, len(track_ids), chunk_size)]

    # Retrieve audio features in chunks
    audio_features = []
    for chunk in chunks:
        audio_features_chunk = sp.audio_features(chunk)
        audio_features.extend(audio_features_chunk)
    audio_features_df = pd.DataFrame(audio_features)

    # Merge track data with audio features
    merged_df = tracks_df.merge(audio_features_df, left_on='id', right_on='id')

    # Prepare the recommendation dataframe
    recommendation_df = merged_df[['name', 'id', 'danceability', 'energy', 'key', 'loudness', 'speechiness', 'acousticness', 'instrumentalness', 'liveness', 'valence', 'tempo']]
    return recommendation_df

# Find song recommendations based on cosine similarity
def rec(song, recommendation_df):
    if recommendation_df is None:
        return

    song = song.lower()
    recommendation_df['name'] = recommendation_df['name'].str.lower()

    # Drop song names and IDs for cosine similarity calculation
    matrix = recommendation_df.drop(['name', 'id'], axis=1)

    # Calculate similarity between tracks
    similarity = cosine_similarity(matrix)

    matching_rows = recommendation_df[recommendation_df['name'].str.contains(song)]
    if matching_rows.empty:
        print("Song not found.")
        return

    # Get similar songs based on similarity score
    idx = matching_rows.index[0]
    similarity_scores = list(enumerate(similarity[idx]))
    sorted_scores = sorted(similarity_scores, key=lambda x: x[1], reverse=True)[1:11]

    # Find top 10 recommendations
    recommendations = []
    for i, score in sorted_scores:
        recommendations.append(recommendation_df.iloc[i]['name'])

    return recommendations

# Get top 10 tracks of an artist
def top10(artist):
    artist_info = sp.search(artist, limit=1, offset=0, type='artist', market=None)
    if not artist_info or not artist_info['artists']['items']:
        print("Artist not found.")
        return

    artist_info = artist_info['artists']['items'][0]
    artist_id = artist_info['id']

    top10tracks = sp.artist_top_tracks(artist_id)['tracks']

    top10_tracks_list = []
    for track in top10tracks[:10]:
        top10_tracks_list.append(track['name'])
    return top10_tracks_list

# Get random song recommendations
def rec_all(artist, recommendation_df, song):
    if recommendation_df is None:
        return

    # Drop song names and IDs for cosine similarity calculation
    matrix = recommendation_df.drop(['name', 'id'], axis=1)

    # Calculate similarity between tracks
    similarity = cosine_similarity(matrix)

    matching_rows = recommendation_df[recommendation_df['name'].str.contains(song)]
    if matching_rows.empty:
        print("Song not found.")
        return

    # Get similar songs based on similarity score
    idx = matching_rows.index[0]
    similarity_scores = list(enumerate(similarity[idx]))
    sorted_scores = sorted(similarity_scores, key=lambda x: x[1], reverse=True)

    # Get top 20 song recommendations
    recommendations = []
    for i, score in sorted_scores[:20]:
        recommendations.append(recommendation_df.iloc[i]['name'])

    return recommendations

# Set up the Telegram bot and add handlers for various commands
def main():
    # Replace 'TOKEN' with your bot token
    updater = Updater('TOKEN', use_context=True)
    dispatcher = updater.dispatcher

    # Add conversation handler with states
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            START: [CommandHandler('discover_artist', discover_artist),
                    CommandHandler('songrec', random_song_rec),
                    CommandHandler('top10', top_10_rec),
                    MessageHandler(Filters.text & ~Filters.command, start)],
            DISCOVER_ARTIST: [MessageHandler(Filters.text & ~Filters.command, discover_artist_input)],
            RANDOM_SONG_REC: [MessageHandler(Filters.text & ~Filters.command, song_rec)],
            ARTIST: [MessageHandler(Filters.text & ~Filters.command, artist_input)],
            SONG: [MessageHandler(Filters.text & ~Filters.command, random_song_rec_input)],
            TOP: [MessageHandler(Filters.text & ~Filters.command, top_10)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    # Add help handler
    dispatcher.add_handler(CommandHandler("help", help_command))

    # Add the conversation handler to the dispatcher
    dispatcher.add_handler(conv_handler)

    # Start the bot
    updater.start_polling()

    # Run the bot until manually stopped
    updater.idle()

if __name__ == '__main__':
    main()
