import DashboardShell from './DashboardShell';   // bestehend
import ChatScreen     from './ChatScreen';       // → enthält <Chat />
import InfoBar        from './components/InfoBar';

export default function DashboardPage() {
  return (
    <DashboardShell>
      <InfoBar />
      <ChatScreen />
    </DashboardShell>
  );
}
