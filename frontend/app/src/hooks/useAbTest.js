import { useCallback, useEffect, useState } from 'react';
import { loadAssignments, trackAbEvent } from '../lib/abtest';

// Returns the copy to show for an experiment plus a `convert` callback to call
// when the visitor acts on it. `fallback` is shown until the assignment arrives
// and whenever the experiment is missing or disabled.
export function useAbTest(testKey, fallback) {
  const [assignment, setAssignment] = useState(null);

  useEffect(() => {
    let live = true;
    loadAssignments().then((all) => {
      if (live) setAssignment(all[testKey] || null);
    });
    return () => {
      live = false;
    };
  }, [testKey]);

  useEffect(() => {
    if (assignment) trackAbEvent(testKey, 'exposure');
  }, [assignment, testKey]);

  const convert = useCallback(() => trackAbEvent(testKey, 'conversion'), [testKey]);

  return { text: assignment?.text || fallback, convert };
}
