#!/bin/zsh

# ./scripts/visualize.sh ../awsgpu-docs/CCTP_af.docx.html.md.converted.md.chunks.jq.embeddings.ndjson.LOCAL

rm -f "$1".emb_values
rm -f "$1".emb_names

for i in {1..$(wc -l "$1" | awk '{print $1;}' )}
do
    echo $(cat "$1" | sed -n "$i"p | jq -r '.embedding[]') | tr ' ' '\t' >> "$1".emb_values

    #echo $(cat "$1" | sed -n "$i"p | jq -r .chunk_id) | tr ' ' '\t' >> "$1".emb_names

    if cat "$1" | sed -n "$i"p | jq -r .text | grep -i forge > /dev/null
    then
    	echo forge >> "$1".emb_names
    else
    	echo autre >> "$1".emb_names
    fi
done

