import { useState, useRef, useCallback } from 'react';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { extractRenderableAssistantText } from './useSealAIStreamContract.js';

export interface WorkingProfile {
  medium?: string;
  pressure_bar?: number;
  temp_range?: [number, number];
  candidate_materials: string[];
  active_hypothesis?: string;
  knowledge_coverage: 'FULL' | 'PARTIAL' | 'LIMITED' | 'UNKNOWN';
  shaft_diameter?: number;
  speed_rpm?: number;
  housing_bore?: number;
  [key: string]: any;
}

export interface Blocker {
  rule_id: string;
  title: string;
  reason: string;
}

export function useSealAIStream(apiEndpoint: string, authToken: string) {
  const [chatHistory, setChatHistory] = useState<{role: 'user'|'ai', text: string}[]>([]);
  const [currentAiText, setCurrentAiText] = useState('');
  const [workingProfile, setWorkingProfile] = useState<WorkingProfile | null>(null);
  const [calcResults, setCalcResults] = useState<any | null>(null);
  const [complianceResults, setComplianceResults] = useState<any | null>(null);
  const [liveCalcTile, setLiveCalcTile] = useState<any | null>(null);
  const [rfqAdmissibility, setRfqAdmissibility] = useState<any | null>(null);
  const [candidateSemantics, setCandidateSemantics] = useState<any[] | null>(null);
  const [governanceMetadata, setGovernanceMetadata] = useState<any | null>(null);
  const [safetyAlerts, setSafetyAlerts] = useState<Blocker[]>([]);
  const [nodeStatus, setNodeStatus] = useState<string | null>(null);
  const [isThinking, setIsThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);
  const lastEventRef = useRef<any>(null);

  const sendMessage = useCallback(async (inputText: string, chatId: string) => {
    if (!inputText.trim()) return;

    setChatHistory(prev => [...prev, { role: 'user', text: inputText }]);
    setCurrentAiText('');
    setSafetyAlerts([]);
    setIsThinking(true);
    setError(null);

    abortControllerRef.current = new AbortController();

    try {
      await fetchEventSource(`${apiEndpoint}/chat/v2`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${authToken}`,
          'X-Request-Id': crypto.randomUUID()
        },
        body: JSON.stringify({ input: inputText, chat_id: chatId }),
        signal: abortControllerRef.current.signal,
        
        async onopen(response) {
          if (response.ok) {
            return;
          }
          
          if (response.status === 409) {
            setError("Eine Antwort wird bereits generiert. Bitte warten Sie, bis diese abgeschlossen ist.");
            throw new Error("Conflict: Already generating response");
          }

          const errorData = await response.json().catch(() => ({}));
          const errorMessage = errorData.message || `Fehler beim Verbinden mit SealAI (${response.status})`;
          setError(errorMessage);
          throw new Error(errorMessage);
        },

        onmessage(ev) {
          const { event, data } = ev;
          lastEventRef.current = { event, data };
          if (!data || data === ': keep-alive') return;
          
          try {
            const payload = JSON.parse(data);
            switch (event) {
              case 'text_chunk':
                setCurrentAiText(prev => prev + payload.text);
                break;
              case 'token':
                if (payload.working_profile) {
                  setWorkingProfile(payload.working_profile);
                }
                const tokenCalcResults =
                  payload.chunk?.working_profile?.calc_results ??
                  payload.working_profile?.calc_results ??
                  payload.chunk?.calc_results ??
                  payload.calc_results;
                if (tokenCalcResults) {
                  setCalcResults(tokenCalcResults);
                }
                const tokenLiveCalcTile =
                  payload.chunk?.working_profile?.live_calc_tile ??
                  payload.working_profile?.live_calc_tile ??
                  payload.chunk?.live_calc_tile ??
                  payload.live_calc_tile;
                if (tokenLiveCalcTile) {
                  setLiveCalcTile(tokenLiveCalcTile);
                }
                setCurrentAiText(prev => {
                  if (prev.endsWith(payload.text)) return prev;
                  if (payload.text.startsWith(prev)) return payload.text;
                  return prev + payload.text;
                });
                break;
              case 'message':
                {
                  const text = extractRenderableAssistantText(payload);
                  if (!text) break;
                  if (payload.replace) {
                    setCurrentAiText(text);
                  } else {
                    setCurrentAiText(prev => prev + text);
                  }
                }
                break;
              case 'done':
                {
                  const text = extractRenderableAssistantText(payload);
                  if (text) {
                    setCurrentAiText(prev => (prev === text || prev.length > text.length ? prev : text));
                  }
                  if (payload.rfq_admissibility) setRfqAdmissibility(payload.rfq_admissibility);
                  if (payload.candidate_semantics) setCandidateSemantics(payload.candidate_semantics);
                  if (payload.governance_metadata) setGovernanceMetadata(payload.governance_metadata);
                  setIsThinking(false);
                }
                break;
              case 'profile_update':
                if (payload.working_profile) {
                  setWorkingProfile(payload.working_profile);
                }
                break;
              case 'state_update':
                const stateText = extractRenderableAssistantText(payload);
                if (stateText) {
                  setCurrentAiText(prev => (prev === stateText || prev.length > stateText.length ? prev : stateText));
                }
                const wp =
                  payload.data?.working_profile ||
                  payload.working_profile ||
                  payload.data?.chunk?.working_profile ||
                  payload.chunk?.working_profile;
                if (wp) setWorkingProfile(wp);

                const cr =
                  payload.data?.working_profile?.calc_results ||
                  payload.working_profile?.calc_results ||
                  payload.data?.chunk?.working_profile?.calc_results ||
                  payload.chunk?.working_profile?.calc_results ||
                  payload.data?.calc_results ||
                  payload.calc_results ||
                  payload.data?.chunk?.calc_results ||
                  payload.chunk?.calc_results;
                if (cr) setCalcResults(cr);

                const cmr = payload.data?.compliance_results || payload.compliance_results;
                if (cmr) setComplianceResults(cmr);

                const rfq =
                  payload.data?.rfq_admissibility ||
                  payload.rfq_admissibility;
                if (rfq) setRfqAdmissibility(rfq);

                const semantics =
                  payload.data?.candidate_semantics ||
                  payload.candidate_semantics;
                if (semantics) setCandidateSemantics(semantics);

                const governance =
                  payload.data?.governance_metadata ||
                  payload.governance_metadata;
                if (governance) setGovernanceMetadata(governance);

                // RWDR Fast-Path: Always update live_calc_tile if present to ensure 16.75 m/s is displayed immediately
                const lct =
                  payload.data?.working_profile?.live_calc_tile ||
                  payload.working_profile?.live_calc_tile ||
                  payload.data?.chunk?.working_profile?.live_calc_tile ||
                  payload.chunk?.working_profile?.live_calc_tile ||
                  payload.data?.live_calc_tile ||
                  payload.live_calc_tile ||
                  payload.data?.chunk?.live_calc_tile ||
                  payload.chunk?.live_calc_tile;
                if (lct) setLiveCalcTile(lct);
                break;
              case 'safety_alert':
                setSafetyAlerts(prev => [...prev, ...payload.blockers]);
                break;
              case 'node_status':
                setNodeStatus(payload.status === 'running' ? payload.node : null);
                break;
              case 'turn_complete':
                setIsThinking(false);
                break;
              case 'error':
                console.error("SealAI Backend Error:", payload.message);
                if (payload.message === "internal_error" && currentAiText.length > 0) {
                  console.warn("Ignoring trailing internal_error since response is complete.");
                  setIsThinking(false);
                  break;
                }
                setError(payload.message || "Ein interner Fehler ist aufgetreten.");
                setIsThinking(false);
                break;
            }
          } catch (err) {
            console.error("Failed to parse SSE payload", err);
          }
        },
        onclose() {
          console.log("LAST EVENT BEFORE END:", lastEventRef.current);
          setIsThinking(false);
        },
        onerror(err) {
          console.error("SSE Connection Error", err);
          setIsThinking(false);
          // Don't throw to avoid retries by fetchEventSource
          // Unless we want it to retry? The requirements imply we should stop on error.
          throw err; 
        }
      });
      
      setCurrentAiText(finalText => {
         if (finalText) setChatHistory(prev => [...prev, { role: 'ai', text: finalText }]);
         return '';
      });

    } catch (error) {
       console.error("Stream aborted or failed", error);
       setIsThinking(false);
    }
  }, [apiEndpoint, authToken]);

  const cancelStream = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setIsThinking(false);
  }, []);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const reset = useCallback(() => {
    cancelStream();
    setChatHistory([]);
    setCurrentAiText('');
    setWorkingProfile(null);
    setCalcResults(null);
    setComplianceResults(null);
    setLiveCalcTile(null);
    setRfqAdmissibility(null);
    setCandidateSemantics(null);
    setGovernanceMetadata(null);
    setSafetyAlerts([]);
    setNodeStatus(null);
    setError(null);
    setIsThinking(false);
  }, [cancelStream]);

  return { chatHistory, currentAiText, workingProfile, calcResults, complianceResults, liveCalcTile, rfqAdmissibility, candidateSemantics, governanceMetadata, safetyAlerts, nodeStatus, isThinking, error, sendMessage, cancelStream, reset, clearError };
}
