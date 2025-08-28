import CcxResultCard from "../../components/CcxResultCard";

export default async function Page({
  params,
}: {
  params: Promise<{ jobId: string }>;
}) {
  const { jobId } = await params;
  return (
    <div className="p-6">
      <CcxResultCard jobId={jobId} />
    </div>
  );
}
