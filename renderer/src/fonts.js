import { staticFile } from 'remotion';

// Fonts ship in public/fonts (SIL Open Font License) so renders never depend on the network.
const FONT_FILES = {
  display: { family: 'Gochi Hand', file: 'fonts/GochiHand-Regular.woff2' },
  label: { family: 'Patrick Hand', file: 'fonts/PatrickHand-Regular.woff2' },
};

export const FONTS = {
  display: `"${FONT_FILES.display.family}", cursive`,
  label: `"${FONT_FILES.label.family}", cursive`,
};

let loading = null;

export function waitForFonts() {
  if (!loading) {
    loading = Promise.all(
      Object.values(FONT_FILES).map(async ({ family, file }) => {
        const face = new FontFace(family, `url(${staticFile(file)}) format('woff2')`);
        await face.load();
        document.fonts.add(face);
      }),
    );
  }
  return loading;
}
