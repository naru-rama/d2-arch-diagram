import { AvoidLib } from '/opt/aws-diagram/node_modules/libavoid-js/dist/index-node.mjs';
import fs from 'node:fs';

await AvoidLib.load('/opt/aws-diagram/node_modules/libavoid-js/dist/libavoid.wasm');
const A = AvoidLib.getInstance();
const spec = JSON.parse(fs.readFileSync(0, 'utf8'));

const router = new A.Router(A.RouterFlag.OrthogonalRouting.value);
for (const [k, v] of Object.entries(spec.params)) router.setRoutingParameter(A.RoutingParameter[k], v);
router.setRoutingParameter(A.RoutingParameter.reverseDirectionPenalty, 500);
router.setRoutingOption(A.RoutingOption.nudgeOrthogonalSegmentsConnectedToShapes, false);
router.setRoutingOption(A.RoutingOption.nudgeSharedPathsWithCommonEndPoint, true);
router.setRoutingOption(A.RoutingOption.performUnifyingNudgingPreprocessingStep, true);
router.setRoutingOption(A.RoutingOption.nudgeOrthogonalTouchingColinearSegments, true);

const DIR = { top: 1, bottom: 2, left: 4, right: 8 };
const rect = ([x1, y1, x2, y2]) => new A.Rectangle(new A.Point(x1, y1), new A.Point(x2, y2));

const shapes = {};
for (const [id, n] of Object.entries(spec.nodes)) {
  shapes[id] = { icon: new A.ShapeRef(router, rect(n.icon)), box: { icon: n.icon } };
  if (n.label) {
    shapes[id].label = new A.ShapeRef(router, rect(n.label));
    shapes[id].box.label = n.label;
  }
}
for (const h of spec.headers) new A.ShapeRef(router, rect(h));

let classId = 1;
const attach = (shape, box, pin) => {
  const [x1, y1, x2, y2] = box;
  const id = classId++;
  const p = new A.ShapeConnectionPin(shape, id, (pin.x - x1) / (x2 - x1), (pin.y - y1) / (y2 - y1), true, 0, DIR[pin.side]);
  p.setExclusive(false);
  return new A.ConnEnd(shape, id);
};
// 枠を障害物にすると中へ線が通れないので、枠線の内側の小さな図形につなぐ
const frameBox = ({ x, y, side }) => ({
  top: [x - 2, y, x + 2, y + 2],
  bottom: [x - 2, y - 2, x + 2, y],
  left: [x, y - 2, x + 2, y + 2],
  right: [x - 2, y - 2, x, y + 2],
})[side];
const end = (pin) => {
  if (pin.shape === 'frame') {
    const box = frameBox(pin);
    return attach(new A.ShapeRef(router, rect(box)), box, pin);
  }
  const s = shapes[pin.node];
  return attach(s[pin.shape], s.box[pin.shape], pin);
};

const conns = spec.edges.map((e) => new A.ConnRef(router, end(e.pins[0]), end(e.pins[1])));
router.processTransaction();

const routes = conns.map((c) => {
  const r = c.displayRoute();
  const pts = [];
  for (let i = 0; i < r.size(); i++) {
    const p = typeof r.at === 'function' ? r.at(i) : r.get_ps(i);
    pts.push([p.x, p.y]);
  }
  return pts;
});
process.stdout.write(JSON.stringify(routes));
