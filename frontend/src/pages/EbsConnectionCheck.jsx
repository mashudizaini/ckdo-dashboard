/**
 * Oracle EBS Connection Check — the HO user's side of EBS Network Monitoring.
 * Open to any logged-in employee (no IT role): IT sends this link to a user
 * who reports EBS as slow, the user runs the test while it is slow, and the
 * result lands in IT > Oracle EBS Network Monitoring > Client Test.
 */
import BrowserTest from "@/pages/dashboard/it/ebsnet/BrowserTest";
import { Note, Panel } from "@/pages/dashboard/it/ebsnet/ui";

export default function EbsConnectionCheck() {
  return (
    <div className="p-6 max-w-5xl">
      <Panel title="Oracle EBS Connection Check" subtitle="A ±20-second test from your laptop to the server at Plant, over the same path as Oracle EBS">
        <Note>
          Run this test <b>while EBS feels slow</b> — do not close EBS first. Choose the current EBS condition, click <b>Start Test</b>,
          then <b>Send results to IT</b>. The test does not change anything on your laptop.
        </Note>
        <div className="h-4" />
        <BrowserTest />
      </Panel>
    </div>
  );
}
