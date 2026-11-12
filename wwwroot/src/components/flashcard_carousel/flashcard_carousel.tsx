import type { ReactNode } from 'react';
import './flashcard_carousel.less';

interface FlashcardCarouselProps {
  /** Changes with every card and side, so the new side slides in. */
  slideKey: string;
  children: ReactNode;
}

const FlashcardCarousel = ({ slideKey, children }: FlashcardCarouselProps) => (
  <div className="flashcard-carousel">
    <div className="flashcard-carousel__slide" key={slideKey}>
      {children}
    </div>
  </div>
);

export default FlashcardCarousel;
