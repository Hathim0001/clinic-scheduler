import { useRunProof } from "../api/hooks";
import { Banner, ErrorBanner, Skeleton } from "../components/common";

/**
 * "Prove the rules": runs the rule scenarios on the server, through the real services and the real
 * database constraints, inside a transaction that is always rolled back. The row counts before and
 * after show that nothing was kept. Nothing here is a simulation in the browser.
 */
export default function Proof() {
  const proof = useRunProof();
  const report = proof.data;

  return (
    <div>
      <h1>Prove the rules</h1>
      <p>
        Each scenario below runs on the server against the real booking rules and the PostgreSQL
        constraints, on its own throwaway doctors and patients and a fixed clock, then the whole run
        is rolled back. It never touches clinic data.
      </p>
      <button
        type="button"
        className="primary"
        onClick={() => proof.mutate()}
        disabled={proof.isPending}
      >
        {proof.isPending ? "Running…" : report ? "Run it again" : "Run the proof"}
      </button>

      {proof.isPending && <Skeleton rows={3} />}
      {proof.error && <ErrorBanner error={proof.error} onRetry={() => proof.mutate()} />}

      {report && (
        <>
          <Banner kind={report.passed ? "success" : "error"}>
            {report.passed
              ? `All ${report.cases.length} scenarios gave the documented answer.`
              : `${report.cases.filter((c) => !c.passed).length} of ${report.cases.length} scenarios did not.`}{" "}
            Rows before the run: {report.rows_before}, after: {report.rows_after}
            {report.rows_before === report.rows_after ? " (nothing kept)." : " (they differ!)."}
          </Banner>
          <div className="table-scroll" role="region" aria-label="Rule scenarios" tabIndex={0}>
            <table>
              <caption className="visually-hidden">Rule scenarios and their results</caption>
              <thead>
                <tr>
                  <th scope="col">Rule</th>
                  <th scope="col">Scenario</th>
                  <th scope="col">Expected</th>
                  <th scope="col">Observed</th>
                  <th scope="col">Result</th>
                </tr>
              </thead>
              <tbody>
                {report.cases.map((c) => (
                  <tr key={c.id}>
                    <th scope="row">{c.rule}</th>
                    <td>{c.scenario}</td>
                    <td>{c.expected}</td>
                    <td>{c.observed}</td>
                    <td>{c.passed ? "Pass" : "FAIL"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
