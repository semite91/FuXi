// The Letterboxd liked movies: the browser reads whether a file is saved and uploads the Learner's likes/films.csv.
// The API checks and keeps the file; the RAG engine reads it from the Settings table.
import { API_URL_KEY, createApiClient } from './api_client';

const GET_LETTERBOXD_LIKES = '/api/GetLetterboxdLikes';
const UPLOAD_LETTERBOXD_LIKES = '/api/UploadLetterboxdLikes';
const FILE_PART = 'file';
const CSV_EXTENSION = '.csv';

export interface LetterboxdLikes {
  hasUpload: boolean;
  movieCount: number;
}

interface LetterboxdLikesSaved {
  movieCount: number;
}

const client = createApiClient(API_URL_KEY);

export const getLetterboxdLikes = (): Promise<LetterboxdLikes> => client.get(GET_LETTERBOXD_LIKES);

/** Saves the file, replacing the earlier one. Returns the number of movies in it. */
export const uploadLetterboxdLikes = async (file: File): Promise<number> =>
  (await client.postFile<LetterboxdLikesSaved>(UPLOAD_LETTERBOXD_LIKES, FILE_PART, file)).movieCount;

/** Only a .csv file is sent; the API checks its columns. */
export const isCsvFile = (file: File): boolean => file.name.toLowerCase().endsWith(CSV_EXTENSION);
