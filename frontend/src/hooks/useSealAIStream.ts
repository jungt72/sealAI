import { useState, useRef, useCallback } from 'react';
import { fetchEventSource } from '@microsoft/fetch-event-source';

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

export function useSealAIStream(apiEndpoint: string, authToken: string) {
  const [chatHistory, setChatHistory] = useState<{role: 'user'|'ai', text: string}[]>([]);
  const [currentAiText, setCurrentAiText] = useState('');
  const [workingProfile, setWorkingProfile] = useState<WorkingProfile | null>(null);
  const [calcResults, setCalcResults] = useState<any | null>(null);
  const [complianceResults, setComplianceResults] = useState<any | null>(null);
  const [liveCalcTile, setLiveCalcTile] = useState<any | null>(null);
  const [nodeStatus, setNodeStatus] = useState<string | null>(null);
  const [isThinking, setIsThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(async (inputText: string, chatId: string) => {
    if (!inputText.trim()) return;

    setChatHistory(prev => [...prev, { role: 'user', text: inputText }]);
    setCurrentAiText('');
    setIsThinking(true);
    setError(null);

    abortControllerRef.current = new AbortController();

    try {
      await fetchEventSource(`${apiEndpoint}/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${authToken}`,
          'X-Request-Id': crypto.randomUUID()
        },
        body: JSON.stringify({ message: inputText, session_id: chatId }),
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
          const { data } = ev;
          if (!data || data === ': keep-alive') return;
          
          if (data === '[DONE]') {
             setIsThinking(false);
             return;
          }

          try {
            const payload = JSON.parse(data);

            if (payload.error) {
              setError(payload.error);
              setIsThinking(false);
              return;
            }

            if (payload.chunk) {
              setCurrentAiText(prev => prev + payload.chunk);
            }

            if (payload.working_profile) {
              setWorkingProfile(payload.working_profile);
              
              const lct = payload.working_profile.live_calc_tile;
              if (lct) setLiveCalcTile(lct);
              
              const cr = payload.working_profile.calc_results;
              if (cr) setCalcResults(cr);
            }

            // state updates (app.agent returns this as payload.state, mapping back to compliance results if necessary later)

          } catch (err) {
            console.error("Failed to parse SSE payload", err);
          }
        },
        onclose() {
          setIsThinking(false);
        },
        onerror(err) {
          console.error("SSE Connection Error", err);
          setIsThinking(false);
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
    setNodeStatus(null);
    setError(null);
    setIsThinking(false);
  }, [cancelStream]);

  return { chatHistory, currentAiText, workingProfile, calcResults, complianceResults, liveCalcTile, nodeStatus, isThinking, error, sendMessage, cancelStream, reset, clearError };
}
