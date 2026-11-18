// The Letterboxd row of the Settings page and its export guide pop-up.
import { useEffect, useState } from 'react';
import { ApiError } from '../services/api_client';
import { getLetterboxdLikes, isCsvFile, uploadLetterboxdLikes, type LetterboxdLikes } from '../services/letterboxd_service';

const NO_UPLOAD: LetterboxdLikes = { hasUpload: false, movieCount: 0 };
const BAD_REQUEST_STATUS = 400;

/** Why an upload failed: the file is not a likes file the API accepts, or anything else. */
export type UploadError = 'notALikesFile' | 'failed';

export const useLetterboxdLikes = () => {
  // Null until the state is known, so an uploaded file never reads "No file uploaded" first.
  const [likes, setLikes] = useState<LetterboxdLikes | null>(null);
  const [isGuideOpen, setIsGuideOpen] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<UploadError | null>(null);

  // The state is read once when the page opens.
  useEffect(() => {
    let isCurrent = true;

    getLetterboxdLikes()
      .catch((): LetterboxdLikes => NO_UPLOAD)
      .then((loaded) => {
        if (isCurrent) {
          setLikes((current) => current ?? loaded);
        }
      });

    return () => {
      isCurrent = false;
    };
  }, []);

  const openGuide = () => {
    setUploadError(null);
    setIsGuideOpen(true);
  };

  const closeGuide = () => setIsGuideOpen(false);

  const upload = async (file: File) => {
    if (isUploading) {
      return;
    }

    if (!isCsvFile(file)) {
      setUploadError('notALikesFile');
      return;
    }

    setIsUploading(true);
    setUploadError(null);
    try {
      const movieCount = await uploadLetterboxdLikes(file);
      setLikes({ hasUpload: true, movieCount });
      setIsGuideOpen(false);
    } catch (error) {
      setUploadError(error instanceof ApiError && error.status === BAD_REQUEST_STATUS ? 'notALikesFile' : 'failed');
    } finally {
      setIsUploading(false);
    }
  };

  return { likes, isGuideOpen, isUploading, uploadError, openGuide, closeGuide, upload };
};
