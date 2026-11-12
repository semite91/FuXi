import './skeleton.less';

const SIZE_CLASSES = {
  line: 'skeleton skeleton--line',
  block: 'skeleton skeleton--block',
  cell: 'skeleton skeleton--cell',
} as const;

interface SkeletonProps {
  size?: keyof typeof SIZE_CLASSES;
}

/** A loading placeholder. The text for screen readers comes from a StatusMessage next to it. */
const Skeleton = ({ size = 'line' }: SkeletonProps) => <span className={SIZE_CLASSES[size]} aria-hidden="true" />;

export default Skeleton;
