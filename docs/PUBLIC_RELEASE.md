# Public release checklist

The project uses MIT for original work, copyright Oliver Granlund / olli.works. Dependencies keep their own licenses. The build bundles dependency notices and font licenses; MIT does not override those terms.

Before changing repository visibility:

- Review all Git history, tags and release assets for credentials, personal logs, Bluetooth addresses and restricted reference material. Ignoring a file or deleting it from the latest commit does not remove history. Rotate any exposed credential before publication. This review is not yet certified complete.
- Review code provenance, including removed files retained in Git history. BikeControl's application license and its MIT protocol specification are separate. Attribution alone does not grant permission to redistribute copied implementation code. Resolve any copied code's actual license before publication.
- Inspect the built ZIP's `legal/THIRD_PARTY_LICENSES.txt` and included font notices. The notice collector includes available installed licenses; it is not a legal compatibility audit or proof that every notice was found.
- Download the actual Windows release on a clean machine and follow the README. Confirm WebView2 prerequisites, keyboard shifting, output-off behavior and log access. Keep unsigned-build and left-controller recovery limitations visible.
- Keep Keyboard as the tested route. Network mode has been reported not working with MyWhoosh and needs diagnosis; do not advertise it as verified. macOS/Linux have shared source, not supported packaged downloads.
- Review GitHub release assets and notes, then change visibility in GitHub Settings only when ready. Public visibility exposes existing history and releases, not just the current README.
- Check that the download works while signed out, enable Issues for reports, and point olli.works to the repository/release. Code signing is a useful later improvement for Windows trust prompts; it is separate from the source license.

Do not claim endorsement by Zwift, MyWhoosh or BikeControl. Use their names to describe compatibility and retain the existing independent-project statement.
