import Landing from "@/components/Landing";
import job from "@/data/job.json";
import type { Job } from "@/lib/types";

export default function Page() {
  return <Landing job={job as unknown as Job} />;
}
