
const assert = require("node:assert/strict");
const http = require("node:http");
const { spawn } = require("node:child_process");
const path = require("node:path");
const fs = require("node:fs");
const root = path.resolve(__dirname, "..");
let writes = 0;
const customer = {id:"c1",customer_name:"Sample customer",order_count:1,lifetime_value:"500",average_order_value:"500",recency_days:2,segment:"NEW_CUSTOMER",tags:[],follow_up_status:"NOT_CONTACTED"};
const fixtures = {
 "/admin/ingestion/summary":{NEW:1,PROCESSING:0,PROCESSED:0,ERROR:1,pending_mapping_items:1},
 "/admin/ingestion":{items:[{id:"r1",source_record_id:"demo",source_system:"HOSTINGER",status:"ERROR",retry_count:0,ingested_at:"2026-09-22",error_message:"order_date is required"}],total:1},
 "/admin/unmapped-products":{items:[{source_system:"HOSTINGER",raw_product_name:"Sample soap",affected_items:1,affected_orders:1,item_revenue:"100",mapping_error:"No match"}],total:1},
 "/admin/products":{items:[],total:0},
 "/admin/customers/c1/follow-ups":{id:"f1"},
 "/customers":{items:[customer],total:1},
 "/admin/customer-segments":{segments:[],thresholds:{high_value:"500",vip_value:"1000",latest_order_date:"2026-09-22"},settings:{new_customer_days:30,active_customer_days:90,champion_recency_days:60,champion_min_orders:3,high_value_percentile:".75",vip_value_percentile:".9"}},
 "/customers/c1":{customer,orders:[],follow_ups:[]},
};
(async () => {
 const backend = http.createServer((req,res) => {
  if(req.method !== "GET") writes++;
  const body = fixtures[new URL(req.url,"http://localhost").pathname];
  res.writeHead(body ? 200 : 404,{"Content-Type":"application/json"});
  res.end(JSON.stringify(body || {detail:"Unknown fixture"}));
 });
 await new Promise(resolve => backend.listen(0,"127.0.0.1",resolve));
 const portProbe = http.createServer();
 await new Promise(resolve => portProbe.listen(0,"127.0.0.1",resolve));
 const port = portProbe.address().port;
 await new Promise(resolve => portProbe.close(resolve));
 const base = "http://127.0.0.1:"+port;
 const child = spawn(process.execPath,[path.join(root,"node_modules/next/dist/bin/next"),"start","-H","127.0.0.1","-p",String(port)],{
  cwd:root, windowsHide:true, env:{...process.env,NODE_ENV:"production",APP_URL:base,API_URL:"http://127.0.0.1:"+backend.address().port,SUPPORT_UI_TOKEN:"smoke-support",ADMIN_API_TOKEN:"smoke-admin",VIEWER_UI_TOKEN:"smoke-viewer",ADMIN_UI_SESSION:"smoke-signing-secret"}
 });
 let logs="";child.stdout.on("data",d=>logs+=d);child.stderr.on("data",d=>logs+=d);
 try {
  let ready=false;
  for(let i=0;i<100;i++) {
   try {if((await fetch(base+"/login")).status===200){ready=true;break;}} catch {}
   await new Promise(resolve=>setTimeout(resolve,200));
  }
  assert.ok(ready,"Next server did not start: "+logs);
  async function login(code) {
   const res=await fetch(base+"/api/login",{method:"POST",body:new URLSearchParams({token:code}),redirect:"manual"});
   assert.equal(res.status,303);assert.equal(res.headers.get("location"),base+(code === "smoke-support" ? "/customers" : "/"));
   return res.headers.getSetCookie().find(v=>v.startsWith("thaazhai_session=")).split(";")[0];
  }
  const viewer=await login("smoke-viewer"),admin=await login("smoke-admin");
  for(const [page,forbidden] of [["/ingestion","Process pending"],["/mappings","Save mapping"],["/customers","Save group rules"]]) {
   const res=await fetch(base+page,{headers:{cookie:viewer}});
   const html=await res.text();
   assert.equal(res.status,200,page);
   assert.ok(html.includes("View-only access"),page);
   // Inspect visible markup only, excluding React's serialized component payload.
   const visible=html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,"");
   assert.ok(!visible.includes(forbidden),page+" exposed write control");
   const adminRes=await fetch(base+page,{headers:{cookie:admin}});
   const adminHtml=await adminRes.text();
   assert.equal(adminRes.status,200,page);
   assert.ok(adminHtml.includes(forbidden),page+" missing admin control");
   if(page==="/ingestion") {
    const jobForm = [...adminHtml.matchAll(/<form\b[^>]*>[\s\S]*?<\/form>/g)].find(match => match[0].includes("Process pending"));
    const action=jobForm?.[0].match(/name="(\$ACTION_ID_[^"]+)"/);
    assert.ok(action,"Expected server action identifier");
    const form=new FormData();form.set(action[1],"");form.set("kind","pending");
    const attempted=await fetch(base+page,{method:"POST",headers:{cookie:viewer,origin:base},body:form,redirect:"manual"});
    assert.ok(attempted.status>=400,"Viewer server action should be rejected");
   }
  }
  assert.equal((await fetch(base+"/api/customers/c1",{headers:{cookie:viewer}})).status,200);
  assert.equal((await fetch(base+"/api/customers/c1/follow-ups",{method:"POST",headers:{cookie:viewer,"Content-Type":"application/json"},body:"{}"})).status,403);
  assert.equal((await fetch(base+"/api/customers/c1")).status,401);

  assert.equal(writes,0,"No unauthorized backend writes");
  const support=await login("smoke-support");
  const customerRes=await fetch(base+"/customers",{headers:{cookie:support}});
  assert.equal(customerRes.status,200);
  const supportHtml=(await customerRes.text()).replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,"");
  assert.ok(supportHtml.includes("Customer support access"));
  assert.ok(!supportHtml.includes("Save group rules"));
  for (const href of ["/ingestion", "/jobs", "/mappings", "/orders"])
    assert.ok(!supportHtml.includes('href="'+href+'"'));
  for (const page of ["/", "/orders", "/ingestion", "/jobs", "/mappings"]) {
    const res=await fetch(base+page,{headers:{cookie:support},redirect:"manual"});
    assert.equal(res.status,303);
    assert.equal(new URL(res.headers.get("location"),base).href,base+"/customers");
  }
  assert.equal((await fetch(base+"/api/customers/c1",{headers:{cookie:support}})).status,200);
  assert.equal((await fetch(base+"/api/admin/jobs",{headers:{cookie:support}})).status,403);
  assert.equal((await fetch(base+"/api/customers/c1/follow-ups",{method:"DELETE",headers:{cookie:support}})).status,403);
  assert.equal(writes,0);
  const followUp=await fetch(base+"/api/customers/c1/follow-ups",{
    method:"POST",headers:{cookie:support,"Content-Type":"application/json"},body:JSON.stringify({notes:"Test contact"})
  });
  assert.equal(followUp.status,201);
  assert.equal(writes,1,"Only the permitted support follow-up reached the backend");

  console.log("Production HTTP smoke passed: all three roles, support page restrictions, customer reads, follow-up write, viewer and support write denials.");
 } finally {
  child.kill();
  await new Promise(resolve=>child.once("exit",resolve));
  await new Promise(resolve=>backend.close(resolve));
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
