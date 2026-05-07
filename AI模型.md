1.当前CLADUE/CODEX CLI可使用
2.kimi: sk-7aLd9kHwkicKYKuOfPX7MZISkT3HtMXdCKa02bbyFTynSfhP
DEEPSEEK: sk-deb34442983c464fa0197a237c6dee14
QWEN:sk-9c0011b9ede14445bb50484313e51d21
小米MIMO:sk-cxwihntxlfjw1392rpsvgjvr4sypfc95ynsihr9y5nepzdyf
豆包：ark-5513f970-ee9f-4a88-9204-264411db214a-8ffb5
豆包调试：
curl https://ark.cn-beijing.volces.com/api/v3/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ark-5513f970-ee9f-4a88-9204-264411db214a-8ffb5" \
  -d $'{
    "model": "doubao-seed-2-0-code-preview-260215",
    "messages": [
        {
            "content": [
                {
                    "image_url": {
                        "url": "https://ark-project.tos-cn-beijing.ivolces.com/images/view.jpeg"
                    },
                    "type": "image_url"
                },
                {
                    "text": "图片主要讲了什么?",
                    "type": "text"
                }
            ],
            "role": "user"
        }
    ]
}'