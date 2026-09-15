# Review a support or RAG assistant

Use **Review saved answers** to check answers from your deployed assistant against your source documents. This path needs no provider key and makes no model calls. **Try sample** demonstrates the process with three fictional answers.

1. Collect a question set, the source documents that apply to those questions, and the assistant's actual answers. Download the starter files for the formats. Use the same `case_id` in the questions and answers; identifiers such as `001` stay text. Record the assistant version and capture time, including time zone.
2. Import the files or paste the three JSON arrays. Check extraction notices against the originals. A PDF page with no searchable text may be blank or scanned; Studio cannot establish its contents. Word tables keep their position and section, and text values in source spreadsheets stay text. Complex layouts still need inspection.
3. Review each answer, returned citation and action against the source. Choose **Supported by the sources**, **Needs a fix**, or **Cannot determine from the sources**. Add a concrete explanation and your name, and select the correct review method. Automatic checks organize evidence but do not complete this review.
4. After changing the assistant, collect replacement answers using the same questions and sources. Upload any subset of the original case IDs with the new version and capture time. Review replacements separately. The comparison identifies reviewed fixes and regressions only for the supplied cases; missing replacements remain untested.
5. Download the report for sharing and **Download workspace to resume later** for continuing your work. The workspace includes the source text, answers and review records. Use **Resume a review** on the home page to upload it in another session. Changed answer or evidence hashes invalidate stale reviews; ambiguous duplicate fields are rejected.

The browser edition runs in the tab without a Streamlit server that sleeps after inactivity. Work remains temporary and is cleared when the tab is closed or reloaded, or the session expires. Keep a workspace download before leaving. It contains your source material and should be shared only with the intended recipients.

An imported capture time, assistant version or reviewer name is supplied attribution, not independently verified identity. Source-review findings do not prove how the assistant retrieved its context, what it cost to run, or how it will perform outside the supplied cases. Missing measurements remain unknown. This workflow does not certify launch readiness.

For a direct model experiment, **Evaluate live assistant** can generate new answers with a supported provider using Studio's source retrieval and prompt. Testing an existing deployed assistant end to end requires its actual answers or an external API connection on an appropriately configured native deployment. The public browser edition does not connect to arbitrary assistant endpoints.
