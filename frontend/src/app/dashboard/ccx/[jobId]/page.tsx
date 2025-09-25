export const dynamic = "force-dynamic";
export const revalidate = 0;

import CcxResultCard from "../../components/CcxResultCard";

export default function Page(props: { params?: { jobId?: string } }) {
  const jobId = props?.params?.jobId ?? "";
  return (
    <div className="p-6">
      {jobId ? (
        <CcxResultCard jobId={jobId} />
      ) : (
        <div className="text-sm text-zinc-500">Keine Job-ID übergeben.</div>
      )}
    </div>
  );
}
