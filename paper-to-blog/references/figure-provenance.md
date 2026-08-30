# Figure provenance

Use this guide whenever selecting, extracting, cropping, validating, or uploading images.

## Allowed

- An image object extracted directly from the paper PDF.
- A lossless crop rendered from the exact PDF page containing the figure or an original subpanel.
- A figure from official supplementary material associated with the same paper.
- Lossless technical conversion needed for platform compatibility when pixels and meaning are preserved.

## Forbidden

- Generated illustrations, graphical abstracts, covers, backgrounds, icons, or replacement charts.
- Redrawing or reconstructing a chart, even from the paper's data.
- AI enhancement, inpainting, upscaling, relabeling, arrow overlays, highlights, or watermarks.
- Images copied from a secondary blog, social post, search result, or unrelated paper.
- Duplicating or splitting images merely to reach an image count.

## Registration requirements

Every displayed image needs one manifest record containing:

- stable local file path and SHA-256;
- original figure label, such as `Figure 2` or `Supplementary Figure S3`;
- one-based PDF page number;
- original or faithfully paraphrased caption;
- source type: `main` or `supplement`;
- extraction method: `embedded` or `page_crop`;
- crop box in PDF points when cropped;
- canonical paper URL or DOI inherited from the paper record.

If the figure label, page, or source cannot be established, do not use the image.

## Selection

Normally use 6-10 figures or subfigures that explain the question, design, main evidence, ablations, errors, and limitations. Use fewer if the paper contains fewer informative figures. Tables may be discussed as text but must not be recreated as images.

## Captions in the blog

Use a visible line such as:

`来源：原论文 Figure 3，PDF 第 7 页；仅作忠实裁剪，DOI: ...`

Do not imply that a cropped subpanel is the complete original figure.
