import VideoWorkspace from "@/components/VideoWorkspace";

export default function VideoPage({ params }: { params: { id: string } }) {
  return <VideoWorkspace videoId={Number(params.id)} />;
}
