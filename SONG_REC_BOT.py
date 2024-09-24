# Import necessary libraries for the bot, Spotify API interaction, and data manipulation
import logging
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, ConversationHandler, CallbackContext
import pandas as pd
import json
import requests
import urllib.parse
import spotipy.util as util
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from sklearn.metrics.pairwise import cosine_similarity

# Set up logging to display info and errors during execution
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Function to get data about an artist and recommend songs
def get_data(artist, song):
    # Spotify API credentials
    client_id = 'CLIENT_ID'
    client_secret = "CLIENT_SECRET"
    username = 'USERNAME'
    scope = 'SCOPE'
    redirect_uri = 'REDIRECT_URL'

    # Authenticate with Spotify using a user token
    token = util.prompt_for_user_token(
        username=username,
        scope=scope,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri
    )

    # Initialize the Spotify client using client credentials
    sp = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(client_id=client_id, client_secret=client_secret))

    # Search for the artist using the Spotify API
    artist_info = sp.search(artist, limit=1, offset=0, type='artist', market=None)
    if not artist_info['artists']['items']:  # If no artist is found, return
        print("Artist not found.")
        return

    # Extract the first artist's information (ID, name, etc.)
    artist_info = artist_info['artists']['items'][0]
    artist_id = artist_info['id']

    # Fetch all albums by the artist (albums, singles, appearances)
    albums = sp.artist_albums(artist_id, album_type=["album", "single", "appears_on"], limit=50)
    albums_df = pd.DataFrame(albums['items'])  # Create a DataFrame from the album data
    tracks_df = pd.DataFrame()  # Initialize an empty DataFrame for track data

    # If the artist has albums, retrieve their tracks
    if not albums_df.empty:
        for album_id in albums_df['id']:
            album_tracks = sp.album_tracks(album_id, limit=50, offset=0, market=None)
            tracks_df = pd.concat([tracks_df, pd.DataFrame(album_tracks['items'])])  # Concatenate track data for each album
    else:
        print("No albums found for this artist.")
        return

    # Reset the index of the tracks DataFrame
    tracks_df = tracks_df.reset_index(drop=True)

    # Get audio features for the tracks (in chunks due to API limits)
    track_ids = tracks_df['id']
    chunk_size = 50  # Maximum allowed by Spotify
    chunks = [track_ids[i:i + chunk_size] for i in range(0, len(track_ids), chunk_size)]
    
    audio_features = []  # Initialize a list to store audio features
    for chunk in chunks:
        audio_features_chunk = sp.audio_features(chunk)  # Retrieve audio features for the chunk
        audio_features.extend(audio_features_chunk)
    
    audio_features_df = pd.DataFrame(audio_features)  # Create a DataFrame for audio features

    # Merge track data with audio features
    merged_df = tracks_df.merge(audio_features_df, left_on='id', right_on='id', suffixes=('', '_audio'))

    # Keep only relevant features for song recommendation
    recommendation_df = merged_df[['name', 'danceability', 'energy', 'key', 'loudness', 'speechiness', 'acousticness', 'instrumentalness', 'liveness', 'valence', 'tempo']]

    # Convert song names to lowercase for comparison
    song = song.lower()
    recommendation_df['name'] = recommendation_df['name'].str.lower()

    # Prepare the features for similarity computation
    x = recommendation_df.drop('name', axis=1)  # Drop the song name column for cosine similarity
    similarity = cosine_similarity(x)  # Compute cosine similarity between songs

    # Find the song entered by the user in the recommendation DataFrame
    print("Looking for song like:", song)
    matching_rows = recommendation_df[recommendation_df['name'].str.contains(song)]  # Find rows matching the input song
    
    if matching_rows.empty:  # If no match found, return
        print("No matching rows found.")
        return
    
    idx = matching_rows.index[0]  # Get the index of the matching song
    distances = sorted(list(enumerate(similarity[idx])), reverse=True, key=lambda x: x[1])  # Sort songs by similarity score

    # Extract the names of the top 10 similar songs
    songs = [recommendation_df.loc[m_id[0], 'name'] for m_id in distances[1:11]]

    # Remove duplicate song names
    recommendations = []
    for song in songs:
        if song not in recommendations:
            recommendations.append(song)

    return recommendations  # Return the list of recommended songs


# Conversation states for user input
ARTIST, SONG = range(2)

# Function to start the conversation and ask for the artist
def start(update: Update, context: CallbackContext) -> int:
    update.message.reply_text("Please enter the artist you want to discover:")
    return ARTIST

# Function to handle the artist input from the user
def receive_artist(update: Update, context: CallbackContext) -> int:
    context.user_data['artist'] = update.message.text  # Store the artist name in user data
    update.message.reply_text("Please enter the song of that artist you like (this may take a few seconds):")
    return SONG

# Function to handle the song input and generate song recommendations
def receive_song(update: Update, context: CallbackContext) -> int:
    artist = context.user_data['artist']  # Retrieve the artist name from user data
    song = update.message.text

    if not artist:
        update.message.reply_text("Please enter the artist first by using /start.")
        return SONG

    try:
        reply = get_data(artist, song)  # Call the get_data function to get recommendations
        
        if not reply:
            update.message.reply_text("No recommendations found for the provided artist and song.")
        else:
            update.message.reply_text(f"Recommended songs: {', '.join(reply)}")
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        update.message.reply_text("An error occurred while processing your request. Please try again later.")
    
    return ConversationHandler.END

# Function to cancel the conversation
def cancel(update: Update, context: CallbackContext) -> int:
    update.message.reply_text("Conversation canceled.")
    return ConversationHandler.END

# Main function to set up the bot
def main():
    while True:  # Run the bot in an infinite loop
        try:
            # Create an Updater with your bot token
            updater = Updater(token="TOKEN", use_context=True)
    
            # Get the dispatcher to register handlers
            dispatcher = updater.dispatcher

            # Create a ConversationHandler with the defined states and functions
            conv_handler = ConversationHandler(
                entry_points=[CommandHandler('start', start)],  # Entry point when user types /start
                states={
                    ARTIST: [MessageHandler(Filters.text & ~Filters.command, receive_artist)],  # Handle artist input
                    SONG: [MessageHandler(Filters.text & ~Filters.command, receive_song)],  # Handle song input
                },
                fallbacks=[CommandHandler('cancel', cancel)],  # Fallback to cancel the conversation
            )
    
            dispatcher.add_handler(conv_handler)  # Add the conversation handler to the dispatcher

            # Start the bot
            updater.start_polling()  # Start polling for user messages
            updater.idle()  # Keep the bot running until interrupted

        except Exception as e:
            logging.error(f"An error occurred: {str(e)}")
            continue

# Entry point for the script
if __name__ == '__main__':
    main()
