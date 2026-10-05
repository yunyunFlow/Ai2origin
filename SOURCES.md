# Interface and version sources

Checked 2026-10-04. These primary sources support interface choices and known
version boundaries; they do not certify this package's runtime.

- [Origin 2021 external Python support](https://blog.originlab.com/accessing-origins-graphing-power-from-python):
  historical context; the article itself notes a newer successor.
- [Application classes](https://docs.originlab.com/com/difference-of-application-applicationsi-and-applicationcomsi/):
  distinct activation/attachment behavior.
- [PutWorksheet](https://docs.originlab.com/com/classes/application/putworksheet/) /
  [GetWorksheet](https://docs.originlab.com/com/classes/application/getworksheet/):
  numerical array transfer and read-back.
- [plotvm](https://docs.originlab.com/x-function/ref/plotvm/):
  virtual-matrix layout and explicit coordinates; API predates 2021.
- [plot_heatmapxyz](https://docs.originlab.com/x-function/ref/plot_heatmapxyz/):
  XYZ heatmaps can perform bin statistics; useful when intentionally requested.
- [Raincloud template](https://www.originlab.com/fileExchange/details.aspx?fid=773):
  minimum 2021, update history and negative-data binning reports.
- [Split-tiles heatmaps](https://www.originlab.com/doc/Origin-Help/Heatmap-SplitTiles):
  a 2024 feature, outside this 2021 baseline.
- [LabTalk set](https://docs.originlab.com/labtalk/ref/set-cmd/):
  line/symbol/fill configuration.
- [Fill modes](https://docs.originlab.com/labtalk/ref/get_options_for_bar_and_column_plots/):
  common-X versus area-enclosed-by-endpoints fill between prepared curves.
- [Page](https://docs.originlab.com/labtalk/ref/page-obj/) /
  [Layer.CMap](https://docs.originlab.com/labtalk/ref/layer-cmap-obj/):
  page base color and explicit color-level settings after rescaling.
- [Numbers in Origin](https://docs.originlab.com/origin-help/number-in-origin/):
  the reserved numerical missing-value sentinel used for padded geometry.

No third-party template, font, installer or model binary is redistributed.
The MIT license covers this package's own code, docs and synthetic samples;
it does not grant a license to Origin or other software.
