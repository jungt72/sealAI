import ChatInterface from "@/components/dashboard/ChatInterface";

export default function DashboardPage() {
    return (
        <div className="flex h-full w-full overflow-hidden bg-white">
            <div className="w-full h-full flex flex-col">
                <ChatInterface />
            </div>
        </div>
    );
}
